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
    
    return user


async def get_current_paid_user(
    user: dict = Depends(get_current_user)
) -> dict:
    """
    Зависимость для проверки оплаченной подписки.
    """
    from datetime import datetime
    
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

