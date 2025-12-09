from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.service import decode_access_token
from app.db import supabase_client
from app.logging_config import get_logger

logger = get_logger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Зависимость для получения текущего пользователя из JWT токена.
    
    Raises:
        HTTPException 401: Если токен невалидный или истёк
        HTTPException 404: Если пользователь не найден
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
    
    Raises:
        HTTPException 402: Если подписка отсутствует или истекла
    """
    paid_until = user.get("paid_until")
    
    if not paid_until:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required"
        )
    
    try:
        if isinstance(paid_until, str):
            paid_until_date = datetime.fromisoformat(paid_until.replace("Z", "+00:00"))
        else:
            paid_until_date = paid_until
        
        now = datetime.now(timezone.utc)
        
        if paid_until_date.tzinfo is None:
            paid_until_date = paid_until_date.replace(tzinfo=timezone.utc)
        
        if paid_until_date < now:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription expired"
            )
    except ValueError as e:
        logger.error(f"Invalid paid_until format: {paid_until}, error: {e}")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Invalid subscription data"
        )
    
    return user
