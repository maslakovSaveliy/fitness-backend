from datetime import date as dt_date, datetime, timezone, timedelta

from app.db import supabase_client
from app.ai import ai_service
from app.ai.prompts import WORKOUT_SPLITS, SPLIT_DESCRIPTIONS
from app.logging_config import get_logger
from app.cache import cache_get, cache_set, make_cache_key, invalidate_user_cache, CacheConfig
from .schemas import WorkoutCreate, WorkoutRateRequest

logger = get_logger(__name__)


async def get_user_workouts(
    user_id: str,
    limit: int = 10,
    offset: int = 0
) -> tuple[list[dict], int]:
    """Получить тренировки пользователя с пагинацией."""
    params = {
        "user_id": f"eq.{user_id}",
        "order": "date.desc",
        "limit": str(limit),
        "offset": str(offset)
    }
    
    workouts, total = await supabase_client.get_with_count("workouts", params)
    
    return workouts, total


async def create_workout(user_id: str, data: WorkoutCreate) -> dict | None:
    """Создать запись о тренировке."""
    workout_date = data.date or dt_date.today()
    
    workout_data = {
        "user_id": user_id,
        "date": workout_date.isoformat(),
        "workout_type": data.workout_type,
        "details": data.details,
    }
    
    if data.calories_burned is not None:
        workout_data["calories_burned"] = data.calories_burned
    
    result = await supabase_client.insert("workouts", workout_data)
    
    if result:
        await invalidate_user_cache(user_id)
        logger.info(f"Workout created for user {user_id}")
    
    return result[0] if result else None


async def generate_workout(user: dict, muscle_group: str | None = None) -> tuple[str, str]:
    """Сгенерировать тренировку через AI."""
    workout_text = await ai_service.generate_workout(user, muscle_group)
    
    used_muscle_group = muscle_group
    if not used_muscle_group:
        custom_frequency = user.get("custom_split_frequency")
        if custom_frequency:
            split = WORKOUT_SPLITS.get(custom_frequency, WORKOUT_SPLITS[3])
        else:
            split = WORKOUT_SPLITS[3]
        used_muscle_group = split[0] if split else "общий комплекс"
    
    return workout_text, used_muscle_group


async def rate_workout(workout_id: str, data: WorkoutRateRequest) -> dict | None:
    """Оценить тренировку."""
    update_data = {"rating": data.rating}
    if data.comment:
        update_data["comment"] = data.comment
    
    result = await supabase_client.update(
        "workouts",
        {"id": f"eq.{workout_id}"},
        update_data
    )
    
    return result[0] if result else None


async def get_workout_stats(user_id: str) -> dict:
    """Получить статистику тренировок с кэшированием."""
    cache_key = make_cache_key("user", user_id, "workout_stats")
    
    cached = await cache_get(cache_key)
    if cached:
        return cached
    
    all_workouts, total_workouts = await supabase_client.get_with_count(
        "workouts",
        {"user_id": f"eq.{user_id}", "select": "id,date"}
    )
    
    current_month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    month_start_iso = current_month_start.isoformat()[:10]
    
    month_workouts, month_count = await supabase_client.get_with_count(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "date": f"gte.{month_start_iso}",
            "select": "id"
        }
    )
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
    cutoff_iso = cutoff_date.isoformat()[:10]
    
    recent_workouts, recent_count = await supabase_client.get_with_count(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "date": f"gte.{cutoff_iso}",
            "select": "id,date"
        }
    )
    average_weekly = round(recent_count / 4.3, 1)
    
    last_workout_date = None
    if all_workouts:
        sorted_workouts = sorted(all_workouts, key=lambda x: x.get("date", ""), reverse=True)
        if sorted_workouts:
            last_workout_date = sorted_workouts[0].get("date")
    
    real_frequency = min(5, max(1, round(average_weekly)))
    recommended_split = SPLIT_DESCRIPTIONS.get(real_frequency, SPLIT_DESCRIPTIONS[3])
    
    result = {
        "total_workouts": total_workouts,
        "month_workouts": month_count,
        "average_weekly": average_weekly,
        "last_workout_date": last_workout_date,
        "current_split": recommended_split,
        "recommended_split": recommended_split
    }
    
    await cache_set(cache_key, result, CacheConfig.WORKOUT_STATS_TTL)
    
    return result


async def get_workout_by_id(workout_id: str, user_id: str) -> dict | None:
    """Получить тренировку по ID."""
    workout = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"}
    )
    return workout
