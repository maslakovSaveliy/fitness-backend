import hmac
import hashlib
import json
from urllib.parse import parse_qs, unquote
from datetime import datetime, timezone, timedelta

import jwt

from app.config import get_settings
from app.logging_config import get_logger
from app.db import supabase_client
from app.utils import user_has_profile
from .schemas import TelegramUser

logger = get_logger(__name__)
settings = get_settings()


def verify_telegram_init_data(init_data: str) -> TelegramUser | None:
    """
    Проверяет подпись initData от Telegram WebApp.
    
    Args:
        init_data: Строка initData из Telegram WebApp
    
    Returns:
        TelegramUser если подпись валидна, иначе None
    """
    try:
        parsed = parse_qs(init_data)
        
        if "hash" not in parsed:
            return None
            
        received_hash = parsed.pop("hash")[0]
        
        data_check_arr = []
        for key in sorted(parsed.keys()):
            value = parsed[key][0]
            data_check_arr.append(f"{key}={value}")
        
        data_check_string = "\n".join(data_check_arr)
        
        secret_key = hmac.new(
            b"WebAppData",
            settings.telegram_bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if calculated_hash != received_hash:
            logger.warning("Invalid Telegram init data signature")
            return None
        
        if "user" in parsed:
            user_data = json.loads(unquote(parsed["user"][0]))
            return TelegramUser(**user_data)
        
        return None
        
    except Exception as e:
        logger.error(f"Error verifying init_data: {e}")
        return None


def create_access_token(telegram_id: int, user_id: str) -> str:
    """
    Создает JWT токен для пользователя.
    
    Args:
        telegram_id: ID пользователя в Telegram
        user_id: ID пользователя в базе данных
    
    Returns:
        JWT токен
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(telegram_id),
        "user_id": user_id,
        "exp": expire
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """
    Декодирует JWT токен.
    
    Args:
        token: JWT токен
    
    Returns:
        Payload токена или None если токен невалидный
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid token: {e}")
        return None


async def get_or_create_user(tg_user: TelegramUser) -> dict | None:
    """
    Получает пользователя из БД или создает нового.
    
    Args:
        tg_user: Данные пользователя из Telegram
    
    Returns:
        Словарь с данными пользователя или None при ошибке
    """
    try:
        user = await supabase_client.get_one(
            "users",
            {"telegram_id": f"eq.{tg_user.id}"}
        )
        
        if user:
            logger.info(f"User {tg_user.id} authenticated")
            return user
        
        new_user = {
            "telegram_id": tg_user.id,
            "username": tg_user.username,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
            "is_paid": False,
            "is_pro": False,
            "trial_expired": False
        }
        
        result = await supabase_client.insert("users", new_user)
        logger.info(f"New user {tg_user.id} created")
        return result[0] if result else None
        
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        return None


__all__ = [
    "verify_telegram_init_data",
    "create_access_token",
    "decode_access_token",
    "get_or_create_user",
    "user_has_profile"
]
