import json
import logging
import random
import re
from openai import AsyncOpenAI
from app.config import get_settings
from app.db import supabase_client
from .prompts import (
    WORKOUT_SPLITS,
    SPLIT_DESCRIPTIONS,
    TIP_TYPES,
    build_workout_prompt,
    build_workout_structured_prompt,
    build_workout_single_exercise_prompt,
    build_manual_workout_infer_prompt,
    build_wellbeing_workout_structured_prompt,
    FOOD_ANALYSIS_PROMPT,
    FOOD_CLARIFICATION_PROMPT,
    DAILY_MENU_SYSTEM_PROMPT,
    SHOPPING_LIST_SYSTEM_PROMPT,
    build_daily_menu_prompt,
    build_daily_menu_structured_prompt,
    build_weekly_menu_structured_prompt,
    build_shopping_list_prompt,
)

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = logging.getLogger(__name__)


class AIService:
    def _details_to_text(self, details_value: object) -> str:
        if details_value is None:
            return ""
        if isinstance(details_value, str):
            return details_value
        if isinstance(details_value, dict):
            # Если это structured workout (dict), лучше превратить в читаемый текст,
            # чтобы работали и "avoid repeats", и история выглядела как в боте.
            try:
                from app.workouts.schemas import WorkoutStructured
                from app.workouts.service import _format_workout_text

                structured = WorkoutStructured.model_validate(details_value)
                return _format_workout_text(structured)
            except Exception:
                try:
                    return json.dumps(details_value, ensure_ascii=False)
                except Exception:
                    return str(details_value)
        return str(details_value)

    async def generate_workout_structured(
        self,
        user: dict,
        target_muscle_group: str | None = None,
        wellbeing_reason: str | None = None,
    ) -> dict:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        exercise_count = random.randint(5, 8)
        tip_type = random.choice(TIP_TYPES)

        attendance_data = await self._calculate_attendance(user["id"])
        real_frequency = attendance_data["real_frequency"]
        recommended_split = attendance_data["recommended_split"]

        use_supersets = self._should_use_supersets(user)

        custom_frequency = user.get("custom_split_frequency")
        if custom_frequency is not None:
            display_frequency = custom_frequency
            display_split = WORKOUT_SPLITS.get(custom_frequency, recommended_split)
        else:
            display_frequency = real_frequency
            display_split = recommended_split

        if target_muscle_group:
            chosen_group = target_muscle_group
        else:
            chosen_group = random.choice(display_split)

        split_description = SPLIT_DESCRIPTIONS.get(display_frequency, SPLIT_DESCRIPTIONS[3])
        split_type = "выбранный" if custom_frequency is not None else "рекомендованный"
        split_info = (
            f"ВАЖНО: Тренировка адаптирована под {split_type} сплит пользователя. "
            f"Пользователь тренируется примерно {display_frequency} раз в неделю. "
            f"{split_type.title()} сплит: {split_description}. "
            f"Сегодня тренируем: {chosen_group}."
        )

        if use_supersets:
            superset_info = (
                "Пользователь предпочитает интенсивные форматы тренировок. "
                "Включи суперсеты там, где это уместно."
            )
        else:
            superset_info = (
                "ВАЖНО: Пользователь отключил суперсеты. НЕ используй суперсеты. "
                "Каждое упражнение должно быть отдельным с отдыхом между подходами."
            )

        workout_history_info, exercises_info = await self._get_workout_history_info(user["id"])

        prompt = build_workout_structured_prompt(
            user=user,
            muscle_group=chosen_group,
            split_info=split_info,
            superset_info=superset_info,
            workout_history_info=workout_history_info,
            exercises_info=exercises_info,
        )

        if wellbeing_reason:
            wellbeing_block = (
                "\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n"
                f"Пользователь не может выполнить полноценную тренировку по причине: {wellbeing_reason}.\n"
                "Составь альтернативную тренировку с учётом этого ограничения.\n"
            )
            prompt = f"{prompt}{wellbeing_block}"

        logger.info(
            "ai_generate_workout_structured_request",
            extra={
                "user_id": user.get("id"),
                "telegram_id": user.get("telegram_id"),
                "chosen_group": chosen_group,
                "exercise_count": exercise_count,
                "use_supersets": use_supersets,
                "custom_split_frequency": custom_frequency,
            },
        )

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=1100,
                response_format={"type": "json_object"},
            )
        except TypeError:
            # На случай старой версии openai SDK, где response_format может отсутствовать
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=1100,
            )

        raw = (response.choices[0].message.content or "").strip()
        parsed = self._extract_json_object(raw)
        if not parsed:
            logger.error(
                "ai_generate_workout_structured_parse_failed",
                extra={
                    "user_id": user.get("id"),
                    "telegram_id": user.get("telegram_id"),
                    "raw_len": len(raw),
                    "raw_preview": raw[:300],
                },
            )

            # Попытка "починки" ответа: попросим вернуть валидный JSON без лишнего текста.
            repair_prompt = (
                "Исправь ответ, чтобы он был ВАЛИДНЫМ JSON-объектом (без Markdown, без пояснений). "
                "Верни только JSON.\n\n"
                f"ВОТ ТЕКУЩИЙ ОТВЕТ:\n{raw}"
            )
            try:
                repair_response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                        {"role": "user", "content": repair_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=1100,
                    response_format={"type": "json_object"},
                )
            except TypeError:
                repair_response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                        {"role": "user", "content": repair_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=1100,
                )

            repaired_raw = (repair_response.choices[0].message.content or "").strip()
            parsed = self._extract_json_object(repaired_raw)
            if not parsed:
                logger.error(
                    "ai_generate_workout_structured_repair_failed",
                    extra={
                        "user_id": user.get("id"),
                        "telegram_id": user.get("telegram_id"),
                        "raw_len": len(repaired_raw),
                        "raw_preview": repaired_raw[:300],
                    },
                )
                raise RuntimeError("AI returned invalid JSON for structured workout")

        normalized = self._normalize_structured_workout(parsed, fallback_muscle_group=chosen_group)
        return normalized

    async def generate_wellbeing_workout_structured(
        self,
        user: dict,
        wellbeing_reason: str,
        avoid_exercise_names: list[str] | None = None,
    ) -> dict:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        attendance_data = await self._calculate_attendance(user["id"])
        real_frequency = attendance_data["real_frequency"]
        recommended_split = attendance_data["recommended_split"]

        use_supersets = self._should_use_supersets(user)

        custom_frequency = user.get("custom_split_frequency")
        if custom_frequency is not None:
            display_frequency = custom_frequency
            display_split = WORKOUT_SPLITS.get(custom_frequency, recommended_split)
        else:
            display_frequency = real_frequency
            display_split = recommended_split

        # Фоллбек-группа нужна только для нормализации, если AI вернёт пусто/мусор.
        fallback_group = random.choice(display_split) if display_split else "общий комплекс"

        split_description = SPLIT_DESCRIPTIONS.get(display_frequency, SPLIT_DESCRIPTIONS[3])
        split_type = "выбранный" if custom_frequency is not None else "рекомендованный"
        split_info = (
            f"ВАЖНО: Тренировка адаптирована под {split_type} сплит пользователя. "
            f"Пользователь тренируется примерно {display_frequency} раз в неделю. "
            f"{split_type.title()} сплит: {split_description}."
        )

        if use_supersets:
            superset_info = (
                "Пользователь предпочитает интенсивные форматы тренировок. "
                "Суперсеты допустимы, но используй их осторожно с учётом самочувствия."
            )
        else:
            superset_info = (
                "ВАЖНО: Пользователь отключил суперсеты. НЕ используй суперсеты. "
                "Каждое упражнение должно быть отдельным."
            )

        workout_history_info, exercises_info = await self._get_workout_history_info(user["id"])

        prompt = build_wellbeing_workout_structured_prompt(
            user=user,
            wellbeing_reason=wellbeing_reason,
            avoid_exercise_names=avoid_exercise_names,
            split_info=split_info,
            superset_info=superset_info,
            workout_history_info=workout_history_info,
            exercises_info=exercises_info,
        )

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=1100,
            response_format={"type": "json_object"},
        )

        raw = (response.choices[0].message.content or "").strip()
        parsed = self._extract_json_object(raw)
        if not parsed:
            raise RuntimeError("AI returned invalid JSON for wellbeing workout")

        normalized = self._normalize_structured_workout(parsed, fallback_muscle_group=fallback_group)
        return normalized

    async def infer_manual_workout_metadata(
        self,
        user: dict,
        exercises: list[dict[str, object]],
    ) -> dict[str, object]:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_manual_workout_infer_prompt(user=user, exercises=exercises)

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=350,
                response_format={"type": "json_object"},
            )
        except TypeError:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=350,
            )

        raw = (response.choices[0].message.content or "").strip()
        parsed = self._extract_json_object(raw)
        if not parsed:
            raise RuntimeError("AI returned invalid JSON for manual workout inference")

        if not isinstance(parsed, dict):
            raise RuntimeError("AI returned invalid object for manual workout inference")

        return parsed

    async def generate_workout_exercise(
        self,
        user: dict,
        muscle_group: str,
        existing_exercise_names: list[str],
    ) -> dict:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        workout_history_info, _ = await self._get_workout_history_info(user["id"])
        superset_info = (
            "ВАЖНО: Пользователь отключил суперсеты. НЕ используй суперсеты. "
            "Каждое упражнение должно быть отдельным."
        )
        if self._should_use_supersets(user):
            superset_info = "Пользователь предпочитает интенсивные форматы тренировок. Суперсеты допустимы."

        prompt = build_workout_single_exercise_prompt(
            user=user,
            muscle_group=muscle_group,
            superset_info=superset_info,
            workout_history_info=workout_history_info,
            existing_exercise_names=existing_exercise_names,
        )

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты фитнес-бот. Возвращай только JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=350,
            response_format={"type": "json_object"},
        )

        raw = (response.choices[0].message.content or "").strip()
        parsed = self._extract_json_object(raw)
        if not parsed:
            raise RuntimeError("AI returned invalid JSON for exercise")

        return self._normalize_exercise(parsed)

    async def generate_workout(
        self,
        user: dict,
        target_muscle_group: str | None = None,
        wellbeing_reason: str | None = None,
    ) -> str:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        exercise_count = random.randint(5, 8)
        tip_type = random.choice(TIP_TYPES)
        
        attendance_data = await self._calculate_attendance(user["id"])
        real_frequency = attendance_data["real_frequency"]
        recommended_split = attendance_data["recommended_split"]
        
        use_supersets = self._should_use_supersets(user)
        
        custom_frequency = user.get("custom_split_frequency")
        if custom_frequency is not None:
            display_frequency = custom_frequency
            display_split = WORKOUT_SPLITS.get(custom_frequency, recommended_split)
        else:
            display_frequency = real_frequency
            display_split = recommended_split
        
        if target_muscle_group:
            chosen_group = target_muscle_group
        else:
            chosen_group = random.choice(display_split)
        
        split_description = SPLIT_DESCRIPTIONS.get(display_frequency, SPLIT_DESCRIPTIONS[3])
        split_type = "выбранный" if custom_frequency is not None else "рекомендованный"
        split_info = (
            f"ВАЖНО: Тренировка адаптирована под {split_type} сплит пользователя. "
            f"Пользователь тренируется примерно {display_frequency} раз в неделю. "
            f"{split_type.title()} сплит: {split_description}. "
            f"Сегодня тренируем: {chosen_group}."
        )
        
        if use_supersets:
            superset_info = (
                "Пользователь предпочитает интенсивные форматы тренировок. "
                "Включи суперсеты там, где это уместно."
            )
        else:
            superset_info = (
                "ВАЖНО: Пользователь отключил суперсеты. НЕ используй суперсеты. "
                "Каждое упражнение должно быть отдельным с отдыхом между подходами."
            )
        
        workout_history_info, exercises_info = await self._get_workout_history_info(user["id"])
        
        prompt = build_workout_prompt(
            user=user,
            muscle_group=chosen_group,
            exercise_count=exercise_count,
            tip_type=tip_type,
            split_info=split_info,
            superset_info=superset_info,
            workout_history_info=workout_history_info,
            exercises_info=exercises_info
        )

        if wellbeing_reason:
            wellbeing_block = (
                "\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n"
                f"Пользователь не может выполнить полноценную тренировку по причине: {wellbeing_reason}.\n"
                "Составь альтернативную тренировку с учётом этого ограничения.\n"
            )
            prompt = f"{prompt}{wellbeing_block}"
        
        logger.info(
            "ai_generate_workout_request",
            extra={
                "user_id": user.get("id"),
                "telegram_id": user.get("telegram_id"),
                "chosen_group": chosen_group,
                "exercise_count": exercise_count,
                "use_supersets": use_supersets,
                "custom_split_frequency": custom_frequency,
            },
        )

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты фитнес-бот. Отвечай всегда только на русском языке."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=1200
        )
        
        workout_text = (response.choices[0].message.content or "").strip()
        if not workout_text:
            logger.error(
                "ai_generate_workout_empty_response",
                extra={"user_id": user.get("id"), "telegram_id": user.get("telegram_id")},
            )
            raise RuntimeError("AI returned empty workout")

        return workout_text

    async def analyze_manual_workout(self, workout_description: str, user: dict) -> str:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        user_info = (
            f"Пол: {user.get('gender', 'не указан')}, "
            f"Возраст: {user.get('age', 'не указан')}, "
            f"Вес: {user.get('weight', 'не указан')} кг, "
            f"Уровень: {user.get('level', 'не указан')}"
        )

        prompt = f"""
Пользователь выполнил тренировку: "{workout_description}"

Информация о пользователе: {user_info}

Проанализируй тренировку и верни JSON в следующем формате:
{{
  "improved_description": "Детальный план прошедшей тренировки",
  "calories_burned": число_калорий,
  "post_workout_advice": "Совет после тренировки"
}}

Требования:
1. improved_description - создай ДЕТАЛЬНЫЙ ПЛАН прошедшей тренировки:
   - тип тренировки
   - список упражнений/нагрузки
   - общее время
   - целевые группы мышц
2. calories_burned - если пользователь указал калории, используй это число, иначе оцени сам.
3. post_workout_advice - дай полезный совет по восстановлению/питанию/следующим тренировкам.

Отвечай только на русском языке.
""".strip()

        logger.info(
            "ai_analyze_manual_workout_request",
            extra={"user_id": user.get("id"), "telegram_id": user.get("telegram_id")},
        )

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Ты персональный тренер и эксперт по фитнесу. Анализируй тренировки пользователей и возвращай только JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=900,
        )

        result = (response.choices[0].message.content or "").strip()
        if not result:
            logger.error("ai_analyze_manual_workout_empty_response")
            raise RuntimeError("AI returned empty manual workout analysis")
        return result

    async def analyze_food_photo(self, image_url: str) -> str:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        logger.info("ai_analyze_food_request", extra={"image_url": image_url})
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": FOOD_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Проанализируй фото и верни JSON."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            max_tokens=500
        )
        result = (response.choices[0].message.content or "").strip()
        if not result:
            logger.error("ai_analyze_food_empty_response", extra={"image_url": image_url})
            raise RuntimeError("AI returned empty food analysis")
        return result

    async def analyze_food_with_clarification(
        self,
        image_url: str,
        clarification: str
    ) -> str:
        prompt = FOOD_CLARIFICATION_PROMPT.format(clarification=clarification)
        logger.info(
            "ai_analyze_food_clarification_request",
            extra={"image_url": image_url, "clarification_len": len(clarification)},
        )
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": clarification},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            max_tokens=500
        )
        result = (response.choices[0].message.content or "").strip()
        if not result:
            logger.error(
                "ai_analyze_food_clarification_empty_response",
                extra={"image_url": image_url},
            )
            raise RuntimeError("AI returned empty food analysis")
        return result

    async def analyze_food_description(self, description: str) -> str:
        """Analyze food from text description only (no photo)."""
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        system_prompt = """Ты эксперт по питанию. Пользователь описывает еду текстом.
Оцени калорийность и БЖУ на основе описания.

ВСЕГДА возвращай ответ в формате JSON:
{
  "description": "уточненное описание блюда",
  "calories": число (ккал),
  "proteins": число (г),
  "fats": число (г),
  "carbs": число (г)
}

Если описание слишком общее, сделай разумные предположения о порции (средняя порция).
Возвращай ТОЛЬКО JSON, без markdown и пояснений."""

        logger.info(
            "ai_analyze_food_description_request",
            extra={"description_len": len(description)},
        )
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": description},
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        
        result = (response.choices[0].message.content or "").strip()
        if not result:
            logger.error("ai_analyze_food_description_empty_response")
            raise RuntimeError("AI returned empty food analysis")
        return result

    async def generate_daily_menu(self, user: dict, nutrition_plan: dict) -> str:
        """Legacy method for text-based menu generation."""
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_daily_menu_prompt(user, nutrition_plan)
        logger.info("ai_generate_daily_menu_request", extra={"user_id": user.get("id")})

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": DAILY_MENU_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=1500,
        )
        menu_text = (response.choices[0].message.content or "").strip()
        if not menu_text:
            raise RuntimeError("AI returned empty daily menu")
        return menu_text

    async def generate_daily_menu_structured(self, user: dict, nutrition_plan: dict) -> dict:
        """Generate structured JSON menu for the day."""
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_daily_menu_structured_prompt(user, nutrition_plan)
        logger.info("ai_generate_daily_menu_structured_request", extra={"user_id": user.get("id")})

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": DAILY_MENU_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
        except TypeError:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": DAILY_MENU_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=2000,
            )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise RuntimeError("AI returned empty daily menu")

        parsed = self._extract_json_object(raw)
        if not parsed:
            logger.error(
                "ai_generate_daily_menu_structured_parse_failed",
                extra={"user_id": user.get("id"), "raw_preview": raw[:300]},
            )
            raise RuntimeError("AI returned invalid JSON for daily menu")

        return self._normalize_daily_menu(parsed, nutrition_plan)

    def _normalize_daily_menu(self, raw: dict, nutrition_plan: dict) -> dict:
        """Normalize and validate the AI-generated menu structure."""
        target_calories = raw.get("target_calories") or nutrition_plan.get("target_calories") or 2000
        target_proteins = raw.get("target_proteins") or nutrition_plan.get("target_proteins") or 100
        target_fats = raw.get("target_fats") or nutrition_plan.get("target_fats") or 70
        target_carbs = raw.get("target_carbs") or nutrition_plan.get("target_carbs") or 250

        sections_raw = raw.get("sections", [])
        if not isinstance(sections_raw, list):
            sections_raw = []

        valid_types = {"breakfast", "lunch", "dinner", "snacks"}
        default_titles = {
            "breakfast": "Завтрак",
            "lunch": "Обед",
            "dinner": "Ужин",
            "snacks": "Перекусы",
        }
        default_time_ranges = {
            "breakfast": "7:00-9:00",
            "lunch": "12:00-14:00",
            "dinner": "18:00-20:00",
            "snacks": "В течение дня",
        }

        sections: list[dict] = []
        for section_raw in sections_raw:
            if not isinstance(section_raw, dict):
                continue

            section_type = section_raw.get("type", "")
            if section_type not in valid_types:
                continue

            title = section_raw.get("title") or default_titles.get(section_type, "")
            time_range = section_raw.get("time_range") or default_time_ranges.get(section_type, "")

            items_raw = section_raw.get("items", [])
            if not isinstance(items_raw, list):
                items_raw = []

            items: list[dict] = []
            for item_raw in items_raw[:5]:
                if not isinstance(item_raw, dict):
                    continue

                name = item_raw.get("name", "")
                if not name or not isinstance(name, str):
                    continue

                calories = item_raw.get("calories", 0)
                proteins = item_raw.get("proteins", 0)
                fats = item_raw.get("fats", 0)
                carbs = item_raw.get("carbs", 0)

                items.append({
                    "name": str(name).strip(),
                    "calories": int(calories) if isinstance(calories, (int, float)) else 0,
                    "proteins": int(proteins) if isinstance(proteins, (int, float)) else 0,
                    "fats": int(fats) if isinstance(fats, (int, float)) else 0,
                    "carbs": int(carbs) if isinstance(carbs, (int, float)) else 0,
                })

            if items:
                sections.append({
                    "type": section_type,
                    "title": str(title).strip(),
                    "time_range": str(time_range).strip(),
                    "items": items,
                })

        tip_of_day = raw.get("tip_of_day", "")
        if not isinstance(tip_of_day, str):
            tip_of_day = "Пейте достаточно воды в течение дня."

        return {
            "target_calories": int(target_calories),
            "target_proteins": int(target_proteins),
            "target_fats": int(target_fats),
            "target_carbs": int(target_carbs),
            "sections": sections,
            "tip_of_day": str(tip_of_day).strip() or "Пейте достаточно воды в течение дня.",
        }

    async def generate_weekly_menu_structured(self, user: dict, nutrition_plan: dict) -> list[dict]:
        """Generate structured JSON menu for 7 days (week)."""
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_weekly_menu_structured_prompt(user, nutrition_plan)
        logger.info("ai_generate_weekly_menu_structured_request", extra={"user_id": user.get("id")})

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": DAILY_MENU_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=8000,
                response_format={"type": "json_object"},
            )
        except TypeError:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": DAILY_MENU_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=8000,
            )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise RuntimeError("AI returned empty weekly menu")

        parsed = self._extract_json_array_or_object(raw)
        if not parsed:
            logger.error(
                "ai_generate_weekly_menu_structured_parse_failed",
                extra={"user_id": user.get("id"), "raw_preview": raw[:500]},
            )
            raise RuntimeError("AI returned invalid JSON for weekly menu")

        return self._normalize_weekly_menu(parsed, nutrition_plan)

    def _extract_json_array_or_object(self, raw: str) -> list | dict | None:
        """Extract JSON array or object from raw response."""
        # Try array first
        array_start = raw.find("[")
        array_end = raw.rfind("]")
        if array_start != -1 and array_end != -1 and array_end > array_start:
            try:
                return json.loads(raw[array_start : array_end + 1])
            except Exception:
                pass
        
        # Fall back to object (might contain array inside)
        obj_start = raw.find("{")
        obj_end = raw.rfind("}")
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            try:
                result = json.loads(raw[obj_start : obj_end + 1])
                # If object contains "days" or "week" array, extract it
                if isinstance(result, dict):
                    for key in ["days", "week", "menus", "menu"]:
                        if key in result and isinstance(result[key], list):
                            return result[key]
                return result
            except Exception:
                pass
        return None

    def _normalize_weekly_menu(self, parsed: list | dict, nutrition_plan: dict) -> list[dict]:
        """Normalize weekly menu to list of 7 day menus."""
        day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        
        # Convert to list if needed
        if isinstance(parsed, dict):
            # Single day - wrap in list
            parsed = [parsed]
        
        if not isinstance(parsed, list):
            raise RuntimeError("Weekly menu must be a list")

        result: list[dict] = []
        for i in range(7):
            if i < len(parsed) and isinstance(parsed[i], dict):
                day_menu = self._normalize_daily_menu(parsed[i], nutrition_plan)
                day_menu["day_of_week"] = i
                day_menu["day_name"] = day_names[i]
            else:
                # Generate empty placeholder for missing day
                day_menu = {
                    "day_of_week": i,
                    "day_name": day_names[i],
                    "target_calories": nutrition_plan.get("target_calories", 2000),
                    "target_proteins": nutrition_plan.get("target_proteins", 100),
                    "target_fats": nutrition_plan.get("target_fats", 70),
                    "target_carbs": nutrition_plan.get("target_carbs", 250),
                    "sections": [],
                    "tip_of_day": "Пейте достаточно воды в течение дня.",
                }
            result.append(day_menu)

        return result

    async def generate_shopping_list(self, daily_menu: str) -> str:
        if not settings.openai_api_key:
            logger.error("openai_api_key_is_missing")
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_shopping_list_prompt(daily_menu)
        logger.info("ai_generate_shopping_list_request")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SHOPPING_LIST_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=800,
        )
        shopping_list = (response.choices[0].message.content or "").strip()
        if not shopping_list:
            raise RuntimeError("AI returned empty shopping list")
        return shopping_list

    async def _calculate_attendance(self, user_id: str) -> dict:
        from datetime import datetime, timedelta
        
        try:
            workouts = await supabase_client.get(
                "workouts",
                {
                    "user_id": f"eq.{user_id}",
                    "status": "eq.completed",
                    "order": "date.desc",
                    "limit": "100",
                }
            )
            
            if not workouts:
                return {
                    "real_frequency": 1,
                    "total_workouts": 0,
                    "average_weekly": 0,
                    "recommended_split": WORKOUT_SPLITS[1]
                }
            
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            recent_workouts = []
            
            for workout in workouts:
                workout_date = datetime.fromisoformat(workout["date"])
                if workout_date >= cutoff_date:
                    recent_workouts.append(workout)
            
            total_workouts = len(recent_workouts)
            weeks_in_period = 30 / 7
            average_weekly = total_workouts / weeks_in_period if weeks_in_period > 0 else 0
            
            real_frequency = min(5, max(1, round(average_weekly)))
            
            return {
                "real_frequency": real_frequency,
                "total_workouts": total_workouts,
                "average_weekly": round(average_weekly, 1),
                "recommended_split": WORKOUT_SPLITS.get(real_frequency, WORKOUT_SPLITS[3])
            }
            
        except Exception as e:
            logger.exception("attendance_calculation_failed", extra={"user_id": user_id})
            return {
                "real_frequency": 3,
                "total_workouts": 0,
                "average_weekly": 0,
                "recommended_split": WORKOUT_SPLITS[3]
            }

    def _should_use_supersets(self, user: dict) -> bool:
        if "supersets_enabled" in user and user["supersets_enabled"] is not None:
            return user["supersets_enabled"]
        
        workout_formats = (user.get("workout_formats") or "").lower()
        
        superset_keywords = ["суперсет", "superset", "круговая", "circuit", "интенсив", "быстро"]
        avoid_keywords = ["классическая", "отдых", "медленно", "новичок"]
        
        if "классическая" in workout_formats:
            return False
        
        if user.get("level", "").lower() in ["новичок", "beginner"]:
            return any(keyword in workout_formats for keyword in superset_keywords)
        
        if any(keyword in workout_formats for keyword in avoid_keywords):
            return False
        
        return any(keyword in workout_formats for keyword in superset_keywords)

    async def _get_workout_history_info(self, user_id: str) -> tuple[str, str]:
        workouts = await supabase_client.get(
            "workouts",
            {
                "user_id": f"eq.{user_id}",
                "status": "eq.completed",
                "order": "date.desc",
                "limit": "3",
            }
        )
        
        workout_history_info = ""
        exercises_info = ""
        
        if workouts:
            workout_history_info = "Последние тренировки пользователя:\n"
            used_exercises = []
            
            for i, w in enumerate(workouts, 1):
                date = w.get("date", "неизвестно")
                workout_type = w.get("workout_type", "")
                rating = w.get("rating")
                details_text = self._details_to_text(w.get("details"))
                details = details_text[:200]
                
                rating_text = f" (оценка: {rating}/5 ⭐)" if rating else " (оценка: не поставлена)"
                comment = w.get("comment")
                comment_text = f"\nКомментарий: {comment}" if comment else ""
                workout_history_info += f"{i}. {date} - {workout_type}{rating_text}{comment_text}\n{details}\n\n"
                
                exercises = self._extract_exercise_names(details_text)
                used_exercises.extend(exercises)
            
            workout_history_info += (
                "Основываясь на этих данных, анализируй предпочтения пользователя по оценкам. "
                "Учитывай что понравилось (высокие оценки) и что не понравилось (низкие оценки). "
                "Особое внимание уделяй комментариям пользователя — они часто содержат конкретные причины недовольства."
            )
            
            unique_exercises = list(set(used_exercises))
            if unique_exercises:
                exercises_info = (
                    f"Упражнения из последних тренировок (по возможности избегай повторов): "
                    f"{', '.join(unique_exercises)}."
                )
        
        return workout_history_info, exercises_info

    def _extract_exercise_names(self, details: str) -> list[str]:
        lines = details.split('\n')
        exercises = []
        for line in lines:
            match = re.match(r'\d+\.\s*([^\n]+)', line)
            if match:
                exercises.append(match.group(1).strip())
        return exercises

    def _extract_json_object(self, raw: str) -> dict | None:
        json_start = raw.find("{")
        json_end = raw.rfind("}")
        if json_start == -1 or json_end == -1 or json_end <= json_start:
            return None
        try:
            return json.loads(raw[json_start : json_end + 1])
        except Exception:
            return None

    def _normalize_structured_workout(self, raw: dict, fallback_muscle_group: str) -> dict:
        # Нормализуем к ожиданиям UI: фиксированный набор reps/weight_kg/sets.
        allowed_reps = [5, 8, 10, 12, 15]
        allowed_weight = [0, 2, 4, 6, 8, 10, 12, 16, 20, 25, 30, 40, 50]
        allowed_sets = [2, 3, 4, 5, 6]
        min_calories = 20
        max_calories = 2000

        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "Тренировка"

        version = raw.get("version")
        if not isinstance(version, int) or version < 1:
            version = 1

        muscle_groups = raw.get("muscle_groups")
        if not isinstance(muscle_groups, list) or not muscle_groups:
            muscle_groups = [str(fallback_muscle_group)]
        muscle_groups = [str(x) for x in muscle_groups[:2]]

        exercises_raw = raw.get("exercises")
        if not isinstance(exercises_raw, list) or not exercises_raw:
            raise RuntimeError("structured workout has empty exercises")

        exercises: list[dict] = []
        for item in exercises_raw[:12]:
            if not isinstance(item, dict):
                continue

            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            reps = item.get("reps")
            if not isinstance(reps, int):
                reps = 12
            reps = min(allowed_reps, key=lambda x: abs(x - reps))

            sets = item.get("sets")
            if not isinstance(sets, int):
                sets = 3
            sets = min(allowed_sets, key=lambda x: abs(x - sets))

            weight = item.get("weight_kg")
            if not isinstance(weight, int):
                weight = 4
            weight = min(allowed_weight, key=lambda x: abs(x - weight))

            exercises.append(
                {"name": name.strip(), "weight_kg": weight, "sets": sets, "reps": reps}
            )

        if not exercises:
            raise RuntimeError("structured workout has no valid exercises")

        calories_raw = raw.get("calories_burned")
        calories_burned: int | None = None
        if isinstance(calories_raw, bool):
            calories_burned = None
        elif isinstance(calories_raw, int):
            calories_burned = calories_raw
        elif isinstance(calories_raw, float):
            calories_burned = int(calories_raw)
        elif isinstance(calories_raw, str):
            try:
                calories_burned = int(float(calories_raw))
            except Exception:
                calories_burned = None

        if isinstance(calories_burned, int):
            calories_burned = max(min_calories, min(max_calories, calories_burned))
        else:
            calories_burned = None

        return {
            "version": int(version),
            "title": str(title).strip(),
            "muscle_groups": muscle_groups,
            "exercises": exercises,
            "calories_burned": calories_burned,
        }

    def _normalize_exercise(self, raw: dict) -> dict:
        allowed_reps = [5, 8, 10, 12, 15]
        allowed_weight = [0, 2, 4, 6, 8, 10, 12, 16, 20, 25, 30, 40, 50]
        allowed_sets = [2, 3, 4, 5, 6]

        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError("exercise has empty name")

        reps = raw.get("reps")
        if not isinstance(reps, int):
            reps = 12
        reps = min(allowed_reps, key=lambda x: abs(x - reps))

        sets = raw.get("sets")
        if not isinstance(sets, int):
            sets = 3
        sets = min(allowed_sets, key=lambda x: abs(x - sets))

        weight = raw.get("weight_kg")
        if not isinstance(weight, int):
            weight = 4
        weight = min(allowed_weight, key=lambda x: abs(x - weight))

        return {"name": name.strip(), "weight_kg": weight, "sets": sets, "reps": reps}

ai_service = AIService()

