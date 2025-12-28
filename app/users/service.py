from datetime import datetime, timedelta
from app.db import supabase_client
from .schemas import ProfileUpdateRequest, SettingsUpdateRequest


def user_has_profile(user: dict) -> bool:
    required_fields = ["goal", "level", "location"]
    return all(user.get(field) for field in required_fields)


async def update_user_profile(user_id: str, data: ProfileUpdateRequest) -> dict:
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return await supabase_client.get_one("users", {"id": f"eq.{user_id}"})
    
    result = await supabase_client.update(
        "users",
        {"id": f"eq.{user_id}"},
        update_data
    )
    return result[0] if result else None


async def update_user_settings(user_id: str, data: SettingsUpdateRequest) -> dict:
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return await supabase_client.get_one("users", {"id": f"eq.{user_id}"})
    
    result = await supabase_client.update(
        "users",
        {"id": f"eq.{user_id}"},
        update_data
    )
    return result[0] if result else None


async def update_last_active(telegram_id: int) -> None:
    now = datetime.utcnow().isoformat()
    try:
        await supabase_client.update(
            "users",
            {"telegram_id": f"eq.{telegram_id}"},
            {"last_active_at": now}
        )
    except Exception as e:
        print(f"Error updating last_active: {e}")


async def deactivate_expired_subscriptions() -> int:
    """
    1-в-1 с bot/db.py:deactivate_expired_subscriptions.
    Без оплат: просто помечаем is_paid=false для просроченных paid_until.
    """
    today = datetime.utcnow().date().isoformat()
    rows = await supabase_client.get(
        "users",
        {
            "paid_until": f"lt.{today}",
            "is_paid": "eq.true",
            "select": "id",
            "limit": "10000",
        },
    )
    if not rows:
        return 0

    updated = 0
    for u in rows:
        user_id = u.get("id")
        if not isinstance(user_id, str):
            continue
        try:
            await supabase_client.update("users", {"id": f"eq.{user_id}"}, {"is_paid": False})
            updated += 1
        except Exception:
            continue
    return updated


async def get_user_stats(user_id: str) -> dict:
    all_workouts = await supabase_client.get(
        "workouts",
        {"user_id": f"eq.{user_id}", "status": "eq.completed", "select": "id,date"}
    )
    total_workouts = len(all_workouts) if all_workouts else 0
    
    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_iso = current_month_start.isoformat()[:10]
    
    month_workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "status": "eq.completed",
            "date": f"gte.{month_start_iso}",
            "select": "id"
        }
    )
    month_count = len(month_workouts) if month_workouts else 0
    
    all_meals = await supabase_client.get(
        "meals",
        {"user_id": f"eq.{user_id}", "select": "id"}
    )
    total_meals = len(all_meals) if all_meals else 0
    
    streak = await calculate_workout_streak(user_id)
    
    return {
        "total_workouts": total_workouts,
        "month_workouts": month_count,
        "total_meals": total_meals,
        "current_streak": streak
    }


async def calculate_workout_streak(user_id: str) -> int:
    workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "status": "eq.completed",
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
    current_date = datetime.utcnow().date()
    
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

