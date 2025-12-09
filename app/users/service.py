from datetime import datetime, timezone, timedelta

from app.db import supabase_client
from app.logging_config import get_logger
from app.cache import cache_get, cache_set, make_cache_key, invalidate_user_cache, CacheConfig
from app.utils import user_has_profile
from .schemas import ProfileUpdateRequest, SettingsUpdateRequest

logger = get_logger(__name__)


async def update_user_profile(user_id: str, data: ProfileUpdateRequest) -> dict:
    """Обновить профиль пользователя."""
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return await supabase_client.get_one("users", {"id": f"eq.{user_id}"})
    
    result = await supabase_client.update(
        "users",
        {"id": f"eq.{user_id}"},
        update_data
    )
    
    await invalidate_user_cache(user_id)
    
    return result[0] if result else None


async def update_user_settings(user_id: str, data: SettingsUpdateRequest) -> dict:
    """Обновить настройки пользователя."""
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return await supabase_client.get_one("users", {"id": f"eq.{user_id}"})
    
    result = await supabase_client.update(
        "users",
        {"id": f"eq.{user_id}"},
        update_data
    )
    
    await invalidate_user_cache(user_id)
    
    return result[0] if result else None


async def update_last_active(telegram_id: int) -> None:
    """Обновить время последней активности пользователя."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        await supabase_client.update(
            "users",
            {"telegram_id": f"eq.{telegram_id}"},
            {"last_active_at": now}
        )
    except Exception as e:
        logger.warning(f"Error updating last_active: {e}")


async def get_user_stats(user_id: str) -> dict:
    """Получить статистику пользователя с кэшированием."""
    cache_key = make_cache_key("user", user_id, "stats")
    
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
    
    all_meals, total_meals = await supabase_client.get_with_count(
        "meals",
        {"user_id": f"eq.{user_id}", "select": "id"}
    )
    
    streak = await calculate_workout_streak(user_id)
    
    result = {
        "total_workouts": total_workouts,
        "month_workouts": month_count,
        "total_meals": total_meals,
        "current_streak": streak
    }
    
    await cache_set(cache_key, result, CacheConfig.USER_STATS_TTL)
    
    return result


async def calculate_workout_streak(user_id: str) -> int:
    """Рассчитать текущую серию тренировок."""
    workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "select": "date",
            "order": "date.desc",
            "limit": "30"
        }
    )
    
    if not workouts:
        return 0
    
    workout_dates = set()
    for w in workouts:
        try:
            date_str = w.get("date", "")[:10]
            workout_dates.add(date_str)
        except Exception:
            continue
    
    streak = 0
    current_date = datetime.now(timezone.utc).date()
    
    while True:
        date_str = current_date.isoformat()
        if date_str in workout_dates:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            if streak == 0 and (current_date + timedelta(days=1)).isoformat() not in workout_dates:
                break
            break
    
    return streak


__all__ = [
    "user_has_profile",
    "update_user_profile",
    "update_user_settings",
    "update_last_active",
    "get_user_stats",
    "calculate_workout_streak"
]
