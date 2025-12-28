import asyncio
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.service import decode_access_token
from app.db import supabase_client

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Зависимость для получения текущего пользователя из JWT токена.
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    user = await supabase_client.get_one("users", {"id": f"eq.{user_id}"})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 1-в-1 с ботом: mark_active делает update last_active_at асинхронно (не блокируя ответ).
    telegram_id = user.get("telegram_id")
    if isinstance(telegram_id, int):
        now_iso = datetime.utcnow().isoformat()

        async def _update_last_active_at() -> None:
            try:
                await supabase_client.update(
                    "users",
                    {"telegram_id": f"eq.{telegram_id}"},
                    {"last_active_at": now_iso},
                )
            except Exception:
                return

        try:
            asyncio.create_task(_update_last_active_at())
        except Exception:
            pass

    return user


async def get_current_paid_user(
    user: dict = Depends(get_current_user)
) -> dict:
    """
    Зависимость для проверки оплаченной подписки.
    """
    if not user.get("is_paid", False):
        # В боте доступ блокируется по флагу is_paid, а текст зависит от trial_expired.
        trial_expired = bool(user.get("trial_expired", False))
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Trial required" if not trial_expired else "Subscription required"
        )

    paid_until = user.get("paid_until")
    
    if not paid_until:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required"
        )
    
    try:
        paid_until_date = datetime.fromisoformat(paid_until.replace("Z", "+00:00"))
        if paid_until_date < datetime.now(paid_until_date.tzinfo):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription expired"
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Invalid subscription data"
        )
    
    return user


async def get_current_admin_user(
    user: dict = Depends(get_current_user)
) -> dict:
    role = user.get("role")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

