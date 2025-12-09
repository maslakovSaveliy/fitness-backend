import random
import re
from datetime import datetime, timezone, timedelta

from openai import AsyncOpenAI, APIError, RateLimitError, APIConnectionError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from app.config import get_settings
from app.logging_config import get_logger
from app.db import supabase_client
from app.cache import (
    cache_get, cache_set, make_cache_key, hash_dict,
    CacheConfig
)
from .prompts import (
    WORKOUT_SPLITS,
    SPLIT_DESCRIPTIONS,
    TIP_TYPES,
    build_workout_prompt,
    FOOD_ANALYSIS_PROMPT,
    FOOD_CLARIFICATION_PROMPT
)

logger = get_logger(__name__)
settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)

OPENAI_RETRYABLE_ERRORS = (APIError, RateLimitError, APIConnectionError)


class AIService:
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(OPENAI_RETRYABLE_ERRORS),
        before_sleep=lambda retry_state: logger.warning(
            f"OpenAI request failed, retrying in {retry_state.next_action.sleep} seconds..."
        )
    )
    async def _call_openai(
        self,
        messages: list[dict],
        max_tokens: int = 1200,
        temperature: float = 0.4
    ) -> str:
        """Вызов OpenAI API с retry логикой."""
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content or ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(OPENAI_RETRYABLE_ERRORS),
        before_sleep=lambda retry_state: logger.warning(
            f"OpenAI Vision request failed, retrying..."
        )
    )
    async def _call_openai_vision(
        self,
        system_prompt: str,
        user_content: list[dict],
        max_tokens: int = 500
    ) -> str:
        """Вызов OpenAI Vision API с retry логикой."""
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=max_tokens
        )
        return response.choices[0].message.content or ""

    async def generate_workout(
        self,
        user: dict,
        target_muscle_group: str | None = None
    ) -> str:
        """Генерация персонализированной тренировки."""
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
        
        logger.info(f"Generating workout for user {user['id']}, muscle group: {chosen_group}")
        
        try:
            workout_text = await self._call_openai(
                messages=[
                    {"role": "system", "content": "Ты фитнес-бот. Отвечай всегда только на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.4
            )
        except Exception as e:
            logger.error(f"Failed to generate workout after retries: {e}")
            raise
        
        await self._update_last_muscle_group(user["telegram_id"], chosen_group)
        
        return workout_text

    async def analyze_food_photo(self, image_url: str) -> str:
        """Анализ фото еды."""
        logger.info(f"Analyzing food photo: {image_url[:50]}...")
        
        try:
            return await self._call_openai_vision(
                system_prompt=FOOD_ANALYSIS_PROMPT,
                user_content=[
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ],
                max_tokens=500
            )
        except Exception as e:
            logger.error(f"Failed to analyze food photo: {e}")
            raise

    async def analyze_food_with_clarification(
        self,
        image_url: str,
        clarification: str
    ) -> str:
        """Анализ фото еды с уточнением от пользователя."""
        prompt = FOOD_CLARIFICATION_PROMPT.format(clarification=clarification)
        
        logger.info(f"Analyzing food photo with clarification: {clarification}")
        
        try:
            return await self._call_openai_vision(
                system_prompt=prompt,
                user_content=[
                    {"type": "text", "text": clarification},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ],
                max_tokens=500
            )
        except Exception as e:
            logger.error(f"Failed to analyze food photo with clarification: {e}")
            raise

    async def _calculate_attendance(self, user_id: str) -> dict:
        """Расчёт посещаемости тренировок с кэшированием."""
        cache_key = make_cache_key("user", user_id, "attendance")
        
        cached = await cache_get(cache_key)
        if cached:
            return cached
        
        try:
            workouts = await supabase_client.get(
                "workouts",
                {"user_id": f"eq.{user_id}", "order": "date.desc", "limit": "100"}
            )
            
            if not workouts:
                result = {
                    "real_frequency": 0,
                    "total_workouts": 0,
                    "average_weekly": 0,
                    "recommended_split": WORKOUT_SPLITS[1]
                }
                await cache_set(cache_key, result, CacheConfig.WORKOUT_STATS_TTL)
                return result
            
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
            recent_workouts = []
            
            for workout in workouts:
                workout_date_str = workout.get("date", "")
                try:
                    if "T" in workout_date_str:
                        workout_date = datetime.fromisoformat(
                            workout_date_str.replace("Z", "+00:00")
                        )
                    else:
                        workout_date = datetime.strptime(
                            workout_date_str, "%Y-%m-%d"
                        ).replace(tzinfo=timezone.utc)
                    
                    if workout_date >= cutoff_date:
                        recent_workouts.append(workout)
                except (ValueError, TypeError):
                    continue
            
            total_workouts = len(recent_workouts)
            weeks_in_period = 30 / 7
            average_weekly = total_workouts / weeks_in_period if weeks_in_period > 0 else 0
            
            real_frequency = min(5, max(1, round(average_weekly)))
            
            result = {
                "real_frequency": real_frequency,
                "total_workouts": total_workouts,
                "average_weekly": round(average_weekly, 1),
                "recommended_split": WORKOUT_SPLITS.get(real_frequency, WORKOUT_SPLITS[3])
            }
            
            await cache_set(cache_key, result, CacheConfig.WORKOUT_STATS_TTL)
            return result
            
        except Exception as e:
            logger.error(f"Error calculating attendance: {e}")
            return {
                "real_frequency": 3,
                "total_workouts": 0,
                "average_weekly": 0,
                "recommended_split": WORKOUT_SPLITS[3]
            }

    def _should_use_supersets(self, user: dict) -> bool:
        """Определить, использовать ли суперсеты."""
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
        """Получить информацию о предыдущих тренировках."""
        workouts = await supabase_client.get(
            "workouts",
            {"user_id": f"eq.{user_id}", "order": "date.desc", "limit": "3"}
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
                details = (w.get("details") or "")[:200]
                
                rating_text = f" (оценка: {rating}/5 ⭐)" if rating else " (оценка: не поставлена)"
                comment = w.get("comment")
                comment_text = f"\nКомментарий: {comment}" if comment else ""
                workout_history_info += f"{i}. {date} - {workout_type}{rating_text}{comment_text}\n{details}\n\n"
                
                exercises = self._extract_exercise_names(w.get("details") or "")
                used_exercises.extend(exercises)
            
            workout_history_info += (
                "Основываясь на этих данных, анализируй предпочтения пользователя по оценкам. "
                "Учитывай что понравилось (высокие оценки) и что не понравилось (низкие оценки)."
            )
            
            unique_exercises = list(set(used_exercises))
            if unique_exercises:
                exercises_info = (
                    f"Упражнения из последних тренировок (по возможности избегай повторов): "
                    f"{', '.join(unique_exercises)}."
                )
        
        return workout_history_info, exercises_info

    def _extract_exercise_names(self, details: str) -> list[str]:
        """Извлечь названия упражнений из текста тренировки."""
        lines = details.split('\n')
        exercises = []
        for line in lines:
            match = re.match(r'\d+\.\s*([^\n]+)', line)
            if match:
                exercises.append(match.group(1).strip())
        return exercises

    async def _update_last_muscle_group(self, telegram_id: int, muscle_group: str) -> None:
        """Обновить последнюю тренированную группу мышц."""
        try:
            await supabase_client.update(
                "users",
                {"telegram_id": f"eq.{telegram_id}"},
                {"last_muscle_group": muscle_group}
            )
        except Exception as e:
            logger.error(f"Error updating last_muscle_group: {e}")


ai_service = AIService()
