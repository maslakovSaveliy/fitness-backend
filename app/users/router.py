from fastapi import APIRouter, Depends, Request

from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.utils import user_has_profile
from .schemas import (
    UserResponse,
    ProfileUpdateRequest,
    SettingsUpdateRequest,
    UserStatsResponse
)
from .service import (
    update_user_profile,
    update_user_settings,
    update_last_active,
    get_user_stats
)

router = APIRouter(prefix="/users", tags=["users"])


def _build_user_response(user: dict) -> UserResponse:
    """Построить ответ с данными пользователя."""
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
        supersets_enabled=user.get("supersets_enabled", False),
        custom_split_frequency=user.get("custom_split_frequency"),
        last_muscle_group=user.get("last_muscle_group"),
        trial_expired=user.get("trial_expired", False),
        has_profile=user_has_profile(user)
    )


@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
async def get_current_user_info(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Получить информацию о текущем пользователе."""
    await update_last_active(user["telegram_id"])
    return _build_user_response(user)


@router.patch("/me/profile", response_model=UserResponse)
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    data: ProfileUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Обновить профиль пользователя (анкета)."""
    updated_user = await update_user_profile(user["id"], data)
    return _build_user_response(updated_user)


@router.patch("/me/settings", response_model=UserResponse)
@limiter.limit("10/minute")
async def update_settings(
    request: Request,
    data: SettingsUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Обновить настройки пользователя."""
    updated_user = await update_user_settings(user["id"], data)
    return _build_user_response(updated_user)


@router.get("/me/stats", response_model=UserStatsResponse)
@limiter.limit("30/minute")
async def get_stats(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Получить статистику пользователя."""
    stats = await get_user_stats(user["id"])
    return UserStatsResponse(**stats)
