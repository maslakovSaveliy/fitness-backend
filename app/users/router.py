from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from .schemas import (
    UserResponse,
    ProfileUpdateRequest,
    SettingsUpdateRequest,
    UserStatsResponse
)
from .service import (
    user_has_profile,
    update_user_profile,
    update_user_settings,
    update_last_active,
    get_user_stats
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Получить информацию о текущем пользователе."""
    await update_last_active(user["telegram_id"])
    
    return UserResponse(
        id=user["id"],
        telegram_id=user["telegram_id"],
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        goal=user.get("goal"),
        level=user.get("level"),
        health_issues=user.get("health_issues"),
        location=user.get("location"),
        workouts_per_week=user.get("workouts_per_week"),
        workout_duration=user.get("workout_duration"),
        equipment=user.get("equipment"),
        workout_formats=user.get("workout_formats"),
        height=user.get("height"),
        weight=user.get("weight"),
        age=user.get("age"),
        gender=user.get("gender"),
        is_paid=user.get("is_paid", False),
        paid_until=user.get("paid_until"),
        is_pro=user.get("is_pro", False),
        supersets_enabled=user.get("supersets_enabled") if user.get("supersets_enabled") is not None else False,
        custom_split_frequency=user.get("custom_split_frequency"),
        last_muscle_group=user.get("last_muscle_group"),
        trial_expired=user.get("trial_expired", False),
        has_profile=user_has_profile(user),
        onboarding_completed=user.get("onboarding_completed", False)
    )


@router.patch("/me/profile", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Обновить профиль пользователя (анкета)."""
    updated_user = await update_user_profile(user["id"], data)
    
    return UserResponse(
        id=updated_user["id"],
        telegram_id=updated_user["telegram_id"],
        username=updated_user.get("username"),
        first_name=updated_user.get("first_name"),
        last_name=updated_user.get("last_name"),
        goal=updated_user.get("goal"),
        level=updated_user.get("level"),
        health_issues=updated_user.get("health_issues"),
        location=updated_user.get("location"),
        workouts_per_week=updated_user.get("workouts_per_week"),
        workout_duration=updated_user.get("workout_duration"),
        equipment=updated_user.get("equipment"),
        workout_formats=updated_user.get("workout_formats"),
        height=updated_user.get("height"),
        weight=updated_user.get("weight"),
        age=updated_user.get("age"),
        gender=updated_user.get("gender"),
        is_paid=updated_user.get("is_paid", False),
        paid_until=updated_user.get("paid_until"),
        is_pro=updated_user.get("is_pro", False),
        supersets_enabled=updated_user.get("supersets_enabled") if updated_user.get("supersets_enabled") is not None else False,
        custom_split_frequency=updated_user.get("custom_split_frequency"),
        last_muscle_group=updated_user.get("last_muscle_group"),
        trial_expired=updated_user.get("trial_expired", False),
        has_profile=user_has_profile(updated_user),
        onboarding_completed=updated_user.get("onboarding_completed", False)
    )


@router.patch("/me/settings", response_model=UserResponse)
async def update_settings(
    data: SettingsUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Обновить настройки пользователя."""
    updated_user = await update_user_settings(user["id"], data)
    
    return UserResponse(
        id=updated_user["id"],
        telegram_id=updated_user["telegram_id"],
        username=updated_user.get("username"),
        first_name=updated_user.get("first_name"),
        last_name=updated_user.get("last_name"),
        goal=updated_user.get("goal"),
        level=updated_user.get("level"),
        health_issues=updated_user.get("health_issues"),
        location=updated_user.get("location"),
        workouts_per_week=updated_user.get("workouts_per_week"),
        workout_duration=updated_user.get("workout_duration"),
        equipment=updated_user.get("equipment"),
        workout_formats=updated_user.get("workout_formats"),
        height=updated_user.get("height"),
        weight=updated_user.get("weight"),
        age=updated_user.get("age"),
        gender=updated_user.get("gender"),
        is_paid=updated_user.get("is_paid", False),
        paid_until=updated_user.get("paid_until"),
        is_pro=updated_user.get("is_pro", False),
        supersets_enabled=updated_user.get("supersets_enabled") if updated_user.get("supersets_enabled") is not None else False,
        custom_split_frequency=updated_user.get("custom_split_frequency"),
        last_muscle_group=updated_user.get("last_muscle_group"),
        trial_expired=updated_user.get("trial_expired", False),
        has_profile=user_has_profile(updated_user),
        onboarding_completed=updated_user.get("onboarding_completed", False)
    )


@router.post("/me/complete-onboarding", response_model=UserResponse)
async def complete_onboarding(user: dict = Depends(get_current_user)):
    """Отметить онбординг как завершенный."""
    from app.db import supabase_client
    
    result = await supabase_client.update(
        "users",
        {"id": f"eq.{user['id']}"},
        {"onboarding_completed": True}
    )
    
    updated_user = result[0] if result else user
    
    return UserResponse(
        id=updated_user["id"],
        telegram_id=updated_user["telegram_id"],
        username=updated_user.get("username"),
        first_name=updated_user.get("first_name"),
        last_name=updated_user.get("last_name"),
        goal=updated_user.get("goal"),
        level=updated_user.get("level"),
        health_issues=updated_user.get("health_issues"),
        location=updated_user.get("location"),
        workouts_per_week=updated_user.get("workouts_per_week"),
        workout_duration=updated_user.get("workout_duration"),
        equipment=updated_user.get("equipment"),
        workout_formats=updated_user.get("workout_formats"),
        height=updated_user.get("height"),
        weight=updated_user.get("weight"),
        age=updated_user.get("age"),
        gender=updated_user.get("gender"),
        is_paid=updated_user.get("is_paid", False),
        paid_until=updated_user.get("paid_until"),
        is_pro=updated_user.get("is_pro", False),
        supersets_enabled=updated_user.get("supersets_enabled") if updated_user.get("supersets_enabled") is not None else False,
        custom_split_frequency=updated_user.get("custom_split_frequency"),
        last_muscle_group=updated_user.get("last_muscle_group"),
        trial_expired=updated_user.get("trial_expired", False),
        has_profile=user_has_profile(updated_user),
        onboarding_completed=True
    )


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_stats(user: dict = Depends(get_current_user)):
    """Получить статистику пользователя."""
    stats = await get_user_stats(user["id"])
    return UserStatsResponse(**stats)

