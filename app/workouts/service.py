from datetime import date as dt_date, datetime, timedelta
from app.db import supabase_client
from app.ai import ai_service
from app.ai.prompts import WORKOUT_SPLITS, SPLIT_DESCRIPTIONS
from .schemas import WorkoutCreate, WorkoutRateRequest


async def get_user_workouts(
    user_id: str,
    limit: int = 10,
    offset: int = 0
) -> tuple[list[dict], int]:
    params = {
        "user_id": f"eq.{user_id}",
        "order": "date.desc",
        "limit": str(limit),
        "offset": str(offset)
    }
    workouts = await supabase_client.get("workouts", params)
    
    count_result = await supabase_client.get(
        "workouts",
        {"user_id": f"eq.{user_id}", "select": "id"}
    )
    total = len(count_result) if count_result else 0
    
    return workouts, total


async def create_workout(user_id: str, data: WorkoutCreate) -> dict:
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
    return result[0] if result else None


async def generate_workout(user: dict, muscle_group: str | None = None) -> tuple[str, str]:
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


async def rate_workout(workout_id: str, data: WorkoutRateRequest) -> dict:
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
    all_workouts = await supabase_client.get(
        "workouts",
        {"user_id": f"eq.{user_id}", "select": "id,date"}
    )
    total_workouts = len(all_workouts) if all_workouts else 0
    
    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_iso = current_month_start.isoformat()[:10]
    
    month_workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "date": f"gte.{month_start_iso}",
            "select": "id"
        }
    )
    month_count = len(month_workouts) if month_workouts else 0
    
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    cutoff_iso = cutoff_date.isoformat()[:10]
    
    recent_workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "date": f"gte.{cutoff_iso}",
            "select": "id,date"
        }
    )
    recent_count = len(recent_workouts) if recent_workouts else 0
    average_weekly = round(recent_count / 4.3, 1)
    
    last_workout_date = None
    if all_workouts:
        sorted_workouts = sorted(all_workouts, key=lambda x: x.get("date", ""), reverse=True)
        if sorted_workouts:
            last_workout_date = sorted_workouts[0].get("date")
    
    real_frequency = min(5, max(1, round(average_weekly)))
    recommended_split = SPLIT_DESCRIPTIONS.get(real_frequency, SPLIT_DESCRIPTIONS[3])
    
    return {
        "total_workouts": total_workouts,
        "month_workouts": month_count,
        "average_weekly": average_weekly,
        "last_workout_date": last_workout_date,
        "current_split": recommended_split,
        "recommended_split": recommended_split
    }


async def get_workout_by_id(workout_id: str, user_id: str) -> dict | None:
    workout = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"}
    )
    return workout

