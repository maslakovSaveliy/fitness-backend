import hmac
import hashlib
import json
import logging
from urllib.parse import parse_qs, unquote
from datetime import datetime, timedelta
from typing import Optional
import jwt
from app.config import get_settings
from app.db import supabase_client
from .schemas import TelegramUser

logger = logging.getLogger(__name__)
settings = get_settings()


def verify_telegram_init_data(init_data: str) -> Optional[TelegramUser]:
    """
    Проверяет подпись initData от Telegram WebApp.
    Возвращает данные пользователя если подпись валидна.
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
            return None
        
        if "user" in parsed:
            user_data = json.loads(unquote(parsed["user"][0]))
            return TelegramUser(**user_data)
        
        return None
        
    except Exception as e:
        print(f"Error verifying init_data: {e}")
        return None


def create_access_token(telegram_id: int, user_id: str) -> str:
    """Создает JWT токен для пользователя."""
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(telegram_id),
        "user_id": user_id,
        "exp": expire
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """Декодирует JWT токен."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_or_create_user(tg_user: TelegramUser) -> dict:
    """
    Получает пользователя из БД или создает нового.
    """
    logger.info(f"[get_or_create_user] Looking for user with telegram_id={tg_user.id}")
    
    user = await supabase_client.get_one(
        "users",
        {"telegram_id": f"eq.{tg_user.id}"}
    )
    
    if user:
        logger.info(f"[get_or_create_user] User found: id={user.get('id')}, has_profile={user.get('has_profile')}")
        return user
    
    logger.info(f"[get_or_create_user] User not found, creating new user")
    new_user = {
        "telegram_id": tg_user.id,
        "username": tg_user.username,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "is_paid": False,
        "is_pro": False,
        "trial_expired": False,
        "has_profile": False,
    }
    
    logger.info(f"[get_or_create_user] Creating user with data: {new_user}")
    
    try:
        result = await supabase_client.insert("users", new_user)
        logger.info(f"[get_or_create_user] User created successfully: {result[0] if result else None}")
        return result[0] if result else None
    except Exception as e:
        logger.error(f"[get_or_create_user] Error creating user: {e}")
        raise


def user_has_profile(user: dict) -> bool:
    """Проверяет, заполнил ли пользователь профиль."""
    required_fields = ["goal", "level", "location"]
    return all(user.get(field) for field in required_fields)

