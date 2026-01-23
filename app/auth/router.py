from fastapi import APIRouter, HTTPException, status
from app.config import get_settings
from .schemas import TelegramAuthRequest, TokenResponse, UserResponse
from .service import (
    verify_telegram_init_data,
    create_access_token,
    get_or_create_user,
    user_has_profile
)
from app.db import supabase_client

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenResponse)
async def authenticate_telegram(request: TelegramAuthRequest):
    """
    Авторизация через Telegram WebApp initData.
    Возвращает JWT токен для дальнейших запросов.
    """
    tg_user = verify_telegram_init_data(request.init_data)
    
    if not tg_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram init data"
        )
    
    user = await get_or_create_user(tg_user)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create or get user"
        )
    
    access_token = create_access_token(tg_user.id, user["id"])
    
    user_response = UserResponse(
        id=user["id"],
        telegram_id=user["telegram_id"],
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        is_paid=user.get("is_paid", False),
        is_pro=user.get("is_pro", False),
        has_profile=user_has_profile(user),
        onboarding_completed=user.get("onboarding_completed", False)
    )
    
    return TokenResponse(
        access_token=access_token,
        user=user_response
    )


@router.post("/dev", response_model=TokenResponse)
async def dev_authenticate():
    """
    Dev-режим авторизации для локального тестирования.
    Работает только если DEBUG=true.
    """
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev auth is only available in debug mode"
        )
    
    user = await supabase_client.get_one(
        "users",
        {"is_paid": "eq.true", "paid_until": f"gt.{__import__('datetime').datetime.now().isoformat()}"}
    )
    
    if not user:
        user = await supabase_client.get_one("users", {})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No users found in database"
        )
    
    access_token = create_access_token(user["telegram_id"], user["id"])
    
    user_response = UserResponse(
        id=user["id"],
        telegram_id=user["telegram_id"],
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        is_paid=user.get("is_paid", False),
        is_pro=user.get("is_pro", False),
        has_profile=user_has_profile(user),
        onboarding_completed=user.get("onboarding_completed", False)
    )
    
    return TokenResponse(
        access_token=access_token,
        user=user_response
    )

