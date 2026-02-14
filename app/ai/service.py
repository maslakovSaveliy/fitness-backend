import asyncio
import logging
import random
import re
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.config import get_settings
from app.db import supabase_client
from .prompts import (
    WORKOUT_SPLITS,
    SPLIT_DESCRIPTIONS,
    TIP_TYPES,
    build_workout_structured_prompt,
    build_workout_single_exercise_prompt,
    build_manual_workout_infer_prompt,
    build_wellbeing_workout_structured_prompt,
    FOOD_ANALYSIS_SYSTEM,
    FOOD_ANALYSIS_USER,
    FOOD_CLARIFICATION_SYSTEM,
    FOOD_DESCRIPTION_SYSTEM,
    MANUAL_WORKOUT_ANALYSIS_SYSTEM,
    DAILY_MENU_SYSTEM,
    SHOPPING_LIST_SYSTEM_PROMPT,
    build_daily_menu_structured_prompt,
    build_shopping_list_prompt,
    TRAINER_CHAT_WORKOUT_SYSTEM,
)
from .schemas import (
    WorkoutAIOutput,
    ExerciseAIOutput,
    WorkoutMetadataAIOutput,
    ManualWorkoutAnalysisAIOutput,
    FoodAnalysisAIOutput,
    DailyMenuAIOutput,
)

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = logging.getLogger(__name__)

MIN_CALORIES = 20
MAX_CALORIES = 2000
MAX_EXERCISE_REPLACE_ATTEMPTS = 3
EXERCISE_REPLACE_TEMP_START = 0.6
EXERCISE_REPLACE_TEMP_STEP = 0.15


class AIService:
    # ------------------------------------------------------------------
    # Workouts
    # ------------------------------------------------------------------

    async def generate_workout_structured(
        self,
        user: dict,
        target_muscle_group: str | None = None,
        wellbeing_reason: str | None = None,
    ) -> dict:
        if not settings.openai_api_key:
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

        chosen_group = target_muscle_group or random.choice(display_split)

        split_description = SPLIT_DESCRIPTIONS.get(display_frequency, SPLIT_DESCRIPTIONS[3])
        split_type = "выбранный" if custom_frequency is not None else "рекомендованный"
        split_info = (
            f"ВАЖНО: Тренировка адаптирована под {split_type} сплит пользователя. "
            f"Пользователь тренируется примерно {display_frequency} раз в неделю. "
            f"{split_type.title()} сплит: {split_description}. "
            f"Сегодня тренируем: {chosen_group}."
        )

        superset_info = self._build_superset_info(use_supersets)
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
            prompt += (
                "\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n"
                f"Пользователь не может выполнить полноценную тренировку по причине: {wellbeing_reason}.\n"
                "Составь альтернативную тренировку с учётом этого ограничения.\n"
            )

        logger.info(
            "ai_generate_workout_structured",
            extra={"user_id": user.get("id"), "chosen_group": chosen_group, "use_supersets": use_supersets},
        )

        parsed = await self._parse(WorkoutAIOutput, prompt, temperature=0.4, max_tokens=1100)
        return self._normalize_structured_workout(parsed, fallback_muscle_group=chosen_group)

    async def generate_wellbeing_workout_structured(
        self,
        user: dict,
        wellbeing_reason: str,
        avoid_exercise_names: list[str] | None = None,
    ) -> dict:
        if not settings.openai_api_key:
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

        fallback_group = random.choice(display_split) if display_split else "общий комплекс"

        split_description = SPLIT_DESCRIPTIONS.get(display_frequency, SPLIT_DESCRIPTIONS[3])
        split_type = "выбранный" if custom_frequency is not None else "рекомендованный"
        split_info = (
            f"ВАЖНО: Тренировка адаптирована под {split_type} сплит пользователя. "
            f"Пользователь тренируется примерно {display_frequency} раз в неделю. "
            f"{split_type.title()} сплит: {split_description}."
        )

        superset_info = self._build_superset_info(use_supersets, wellbeing=True)
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

        parsed = await self._parse(WorkoutAIOutput, prompt, temperature=0.4, max_tokens=1100)
        return self._normalize_structured_workout(parsed, fallback_muscle_group=fallback_group)

    async def infer_manual_workout_metadata(
        self,
        user: dict,
        exercises: list[dict[str, object]],
    ) -> dict[str, object]:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_manual_workout_infer_prompt(user=user, exercises=exercises)
        parsed = await self._parse(WorkoutMetadataAIOutput, prompt, temperature=0.2, max_tokens=350)
        return parsed.model_dump()

    async def generate_workout_exercise(
        self,
        user: dict,
        muscle_group: str,
        existing_exercise_names: list[str],
    ) -> dict:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        workout_history_info, _ = await self._get_workout_history_info(user["id"])
        superset_info = self._build_superset_info(self._should_use_supersets(user))

        prompt = build_workout_single_exercise_prompt(
            user=user,
            muscle_group=muscle_group,
            superset_info=superset_info,
            workout_history_info=workout_history_info,
            existing_exercise_names=existing_exercise_names,
        )

        existing_lower = {n.lower().strip() for n in existing_exercise_names}
        temperature = EXERCISE_REPLACE_TEMP_START
        last_parsed: ExerciseAIOutput | None = None

        for attempt in range(MAX_EXERCISE_REPLACE_ATTEMPTS):
            parsed = await self._parse(ExerciseAIOutput, prompt, temperature=temperature, max_tokens=350)
            last_parsed = parsed

            if parsed.name.lower().strip() not in existing_lower:
                return {"name": parsed.name.strip(), "weight_kg": parsed.weight_kg, "sets": parsed.sets, "reps": parsed.reps}

            logger.warning("exercise_replacement_duplicate attempt=%d name=%s", attempt + 1, parsed.name)
            temperature = min(temperature + EXERCISE_REPLACE_TEMP_STEP, 1.0)

        return {"name": last_parsed.name.strip(), "weight_kg": last_parsed.weight_kg, "sets": last_parsed.sets, "reps": last_parsed.reps}

    # ------------------------------------------------------------------
    # Manual workout analysis
    # ------------------------------------------------------------------

    async def analyze_manual_workout(self, workout_description: str, user: dict) -> ManualWorkoutAnalysisAIOutput:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        user_info = (
            f"Пол: {user.get('gender', 'не указан')}, "
            f"Возраст: {user.get('age', 'не указан')}, "
            f"Вес: {user.get('weight', 'не указан')} кг, "
            f"Уровень: {user.get('level', 'не указан')}"
        )

        prompt = (
            f'Пользователь выполнил тренировку: "{workout_description}"\n'
            f"Информация о пользователе: {user_info}\n\n"
            "Требования:\n"
            "1. improved_description — детальный план прошедшей тренировки (тип, упражнения, время, группы мышц).\n"
            "2. calories_burned — оценка сожжённых калорий.\n"
            "3. post_workout_advice — совет по восстановлению/питанию."
        )

        logger.info("ai_analyze_manual_workout", extra={"user_id": user.get("id")})
        return await self._parse(
            ManualWorkoutAnalysisAIOutput,
            prompt,
            system=MANUAL_WORKOUT_ANALYSIS_SYSTEM,
            temperature=0.4,
            max_tokens=900,
        )

    # ------------------------------------------------------------------
    # Food analysis
    # ------------------------------------------------------------------

    async def analyze_food_photo(self, image_url: str) -> FoodAnalysisAIOutput:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        logger.info("ai_analyze_food_photo", extra={"image_url": image_url[:80]})
        return await self._parse_vision(
            FoodAnalysisAIOutput,
            system=FOOD_ANALYSIS_SYSTEM,
            text=FOOD_ANALYSIS_USER,
            image_url=image_url,
            max_tokens=500,
        )

    async def analyze_food_with_clarification(self, image_url: str, clarification: str) -> FoodAnalysisAIOutput:
        logger.info("ai_analyze_food_clarification", extra={"image_url": image_url[:80]})
        system = FOOD_CLARIFICATION_SYSTEM.format(clarification=clarification)
        return await self._parse_vision(
            FoodAnalysisAIOutput,
            system=system,
            text=clarification,
            image_url=image_url,
            max_tokens=500,
        )

    async def analyze_food_description(self, description: str) -> FoodAnalysisAIOutput:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        logger.info("ai_analyze_food_description", extra={"description_len": len(description)})
        return await self._parse(
            FoodAnalysisAIOutput,
            description,
            system=FOOD_DESCRIPTION_SYSTEM,
            temperature=0.3,
            max_tokens=300,
        )

    # ------------------------------------------------------------------
    # Nutrition menus
    # ------------------------------------------------------------------

    async def generate_daily_menu_structured(
        self,
        user: dict,
        nutrition_plan: dict,
        day_name: str = "",
    ) -> DailyMenuAIOutput:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_daily_menu_structured_prompt(user, nutrition_plan, day_name=day_name)
        logger.info("ai_generate_daily_menu_structured", extra={"user_id": user.get("id"), "day_name": day_name})
        return await self._parse(
            DailyMenuAIOutput,
            prompt,
            system=DAILY_MENU_SYSTEM,
            temperature=0.8,
            max_tokens=2000,
        )

    async def generate_weekly_menu_structured(self, user: dict, nutrition_plan: dict) -> list[dict]:
        """7 параллельных запросов — по одному на каждый день."""
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

        async def _gen_day(index: int, name: str) -> dict:
            try:
                parsed = await self.generate_daily_menu_structured(user, nutrition_plan, day_name=name)
                result = parsed.model_dump()
                result["day_of_week"] = index
                result["day_name"] = name
                return result
            except Exception as exc:
                logger.error("weekly_menu_day_failed day=%s error=%s", name, exc)
                return self._empty_day_menu(index, name, nutrition_plan)

        tasks = [_gen_day(i, name) for i, name in enumerate(day_names)]
        return list(await asyncio.gather(*tasks))

    async def generate_shopping_list(self, daily_menu: str) -> str:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is missing")

        prompt = build_shopping_list_prompt(daily_menu)
        logger.info("ai_generate_shopping_list")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SHOPPING_LIST_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=800,
        )
        result = (response.choices[0].message.content or "").strip()
        if not result:
            raise RuntimeError("AI returned empty shopping list")
        return result

    # ------------------------------------------------------------------
    # Trainer chat (streaming)
    # ------------------------------------------------------------------

    async def stream_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int = 450,
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks from a streaming chat completion."""
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def generate_trainer_workout(
        self,
        chat_messages: list[dict[str, str]],
    ) -> WorkoutAIOutput:
        """Финализация чата с тренером: structured output для тренировки."""
        response = await client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=chat_messages,
            response_format=WorkoutAIOutput,
            temperature=0.4,
            max_tokens=1100,
        )
        parsed = response.choices[0].message.parsed
        if not parsed:
            raise RuntimeError("AI returned invalid workout from trainer chat")
        return parsed

    # ------------------------------------------------------------------
    # Internal: structured output helpers
    # ------------------------------------------------------------------

    async def _parse(
        self,
        schema: type,
        user_prompt: str,
        *,
        system: str = "Ты фитнес-бот. Отвечай ТОЛЬКО на русском языке. Все названия упражнений, советы и текст — на русском.",
        temperature: float = 0.4,
        max_tokens: int = 1100,
    ):
        """Single-shot structured output via beta.chat.completions.parse."""
        response = await client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            response_format=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parsed = response.choices[0].message.parsed
        if not parsed:
            refusal = response.choices[0].message.refusal
            logger.error("ai_structured_output_failed schema=%s refusal=%s", schema.__name__, refusal)
            raise RuntimeError(f"AI refused to generate {schema.__name__}: {refusal}")
        return parsed

    async def _parse_vision(
        self,
        schema: type,
        *,
        system: str,
        text: str,
        image_url: str,
        max_tokens: int = 500,
    ):
        """Structured output for vision (image) requests."""
        response = await client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            response_format=schema,
            max_tokens=max_tokens,
        )
        parsed = response.choices[0].message.parsed
        if not parsed:
            refusal = response.choices[0].message.refusal
            logger.error("ai_vision_parse_failed schema=%s refusal=%s", schema.__name__, refusal)
            raise RuntimeError(f"AI refused vision analysis: {refusal}")
        return parsed

    # ------------------------------------------------------------------
    # Internal: workout normalization (business-logic only)
    # ------------------------------------------------------------------

    def _normalize_structured_workout(self, parsed: WorkoutAIOutput, fallback_muscle_group: str) -> dict:
        exercises: list[dict] = []
        seen_names: set[str] = set()

        skip_prefixes = ("*", "совет", "важно", "следите", "не забудь", "обратите внимание", "рекоменд", "старайтесь", "помните")

        for ex in parsed.exercises[:12]:
            name = ex.name.strip()
            name_lower = name.lower()

            if any(name_lower.startswith(kw) for kw in skip_prefixes):
                continue
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            exercises.append({"name": name, "weight_kg": ex.weight_kg, "sets": ex.sets, "reps": ex.reps})

        if not exercises:
            raise RuntimeError("structured workout has no valid exercises")

        muscle_groups = [str(g) for g in parsed.muscle_groups[:2]]
        requested_parts = [p.strip().lower() for p in fallback_muscle_group.split(",") if p.strip()]
        if requested_parts:
            ai_lower = [g.lower() for g in muscle_groups]
            has_overlap = any(rp in ag or ag in rp for rp in requested_parts for ag in ai_lower)
            if not has_overlap:
                muscle_groups = [p.strip() for p in fallback_muscle_group.split(",") if p.strip()][:2]

        calories = parsed.calories_burned
        calories = max(MIN_CALORIES, min(MAX_CALORIES, calories)) if calories else None

        wellbeing_advice = parsed.wellbeing_advice
        if wellbeing_advice:
            wellbeing_advice = wellbeing_advice.strip()[:500]

        return {
            "version": 1,
            "title": parsed.title.strip() or "Тренировка",
            "muscle_groups": muscle_groups,
            "exercises": exercises,
            "estimated_calories": calories,
            "wellbeing_advice": wellbeing_advice,
        }

    @staticmethod
    def _empty_day_menu(index: int, name: str, nutrition_plan: dict) -> dict:
        return {
            "day_of_week": index,
            "day_name": name,
            "target_calories": nutrition_plan.get("target_calories", 2000),
            "target_proteins": nutrition_plan.get("target_proteins", 100),
            "target_fats": nutrition_plan.get("target_fats", 70),
            "target_carbs": nutrition_plan.get("target_carbs", 250),
            "sections": [],
            "tip_of_day": "Пейте достаточно воды в течение дня.",
        }

    # ------------------------------------------------------------------
    # Internal: attendance & history helpers
    # ------------------------------------------------------------------

    async def _calculate_attendance(self, user_id: str) -> dict:
        from datetime import datetime, timedelta

        try:
            workouts = await supabase_client.get(
                "workouts",
                {"user_id": f"eq.{user_id}", "status": "eq.completed", "order": "date.desc", "limit": "100"},
            )

            if not workouts:
                return {"real_frequency": 1, "total_workouts": 0, "average_weekly": 0, "recommended_split": WORKOUT_SPLITS[1]}

            cutoff_date = datetime.utcnow() - timedelta(days=30)
            recent_workouts = [w for w in workouts if datetime.fromisoformat(w["date"]) >= cutoff_date]
            total = len(recent_workouts)
            avg_weekly = total / (30 / 7) if total else 0
            real_frequency = min(5, max(1, round(avg_weekly)))

            return {
                "real_frequency": real_frequency,
                "total_workouts": total,
                "average_weekly": round(avg_weekly, 1),
                "recommended_split": WORKOUT_SPLITS.get(real_frequency, WORKOUT_SPLITS[3]),
            }
        except Exception:
            logger.exception("attendance_calculation_failed user_id=%s", user_id)
            return {"real_frequency": 3, "total_workouts": 0, "average_weekly": 0, "recommended_split": WORKOUT_SPLITS[3]}

    def _should_use_supersets(self, user: dict) -> bool:
        if "supersets_enabled" in user and user["supersets_enabled"] is not None:
            return user["supersets_enabled"]

        workout_formats = (user.get("workout_formats") or "").lower()
        superset_keywords = ["суперсет", "superset", "круговая", "circuit", "интенсив", "быстро"]

        if "классическая" in workout_formats:
            return False
        if user.get("level", "").lower() in ["новичок", "beginner"]:
            return any(kw in workout_formats for kw in superset_keywords)
        if any(kw in workout_formats for kw in ["классическая", "отдых", "медленно", "новичок"]):
            return False
        return any(kw in workout_formats for kw in superset_keywords)

    @staticmethod
    def _build_superset_info(use_supersets: bool, *, wellbeing: bool = False) -> str:
        if use_supersets:
            base = "Пользователь предпочитает интенсивные форматы тренировок."
            if wellbeing:
                return f"{base} Суперсеты допустимы, но используй их осторожно с учётом самочувствия."
            return f"{base} Включи суперсеты там, где это уместно."
        return "ВАЖНО: Пользователь отключил суперсеты. НЕ используй суперсеты. Каждое упражнение должно быть отдельным с отдыхом между подходами."

    def _details_to_text(self, details_value: object) -> str:
        if details_value is None:
            return ""
        if isinstance(details_value, str):
            return details_value
        if isinstance(details_value, dict):
            try:
                from app.workouts.schemas import WorkoutStructured
                from app.workouts.service import _format_workout_text

                structured = WorkoutStructured.model_validate(details_value)
                return _format_workout_text(structured)
            except Exception:
                try:
                    import json
                    return json.dumps(details_value, ensure_ascii=False)
                except Exception:
                    return str(details_value)
        return str(details_value)

    async def _get_workout_history_info(self, user_id: str) -> tuple[str, str]:
        workouts = await supabase_client.get(
            "workouts",
            {"user_id": f"eq.{user_id}", "status": "eq.completed", "order": "date.desc", "limit": "3"},
        )

        workout_history_info = ""
        exercises_info = ""

        if workouts:
            workout_history_info = "Последние тренировки пользователя:\n"
            used_exercises: list[str] = []

            for i, w in enumerate(workouts, 1):
                date = w.get("date", "неизвестно")
                workout_type = w.get("workout_type", "")
                rating = w.get("rating")
                details_text = self._details_to_text(w.get("details"))
                details = details_text[:200]

                rating_text = f" (оценка: {rating}/5)" if rating else " (оценка: не поставлена)"
                comment = w.get("comment")
                comment_text = f"\nКомментарий: {comment}" if comment else ""
                workout_history_info += f"{i}. {date} - {workout_type}{rating_text}{comment_text}\n{details}\n\n"

                exercises = self._extract_exercise_names(details_text)
                used_exercises.extend(exercises)

            workout_history_info += (
                "Основываясь на этих данных, анализируй предпочтения пользователя по оценкам. "
                "Учитывай что понравилось (высокие оценки) и что не понравилось (низкие оценки). "
                "Особое внимание уделяй комментариям пользователя."
            )

            unique_exercises = list(set(used_exercises))
            if unique_exercises:
                exercises_info = f"Упражнения из последних тренировок (по возможности избегай повторов): {', '.join(unique_exercises)}."

        return workout_history_info, exercises_info

    @staticmethod
    def _extract_exercise_names(details: str) -> list[str]:
        return [
            match.group(1).strip()
            for line in details.split("\n")
            if (match := re.match(r"\d+\.\s*([^\n]+)", line))
        ]


ai_service = AIService()
