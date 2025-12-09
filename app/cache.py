import json
import hashlib
from typing import TypeVar, Callable, ParamSpec
from functools import wraps
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


class CacheConfig:
    """Константы для TTL кэша в секундах."""
    
    USER_STATS_TTL = 300  # 5 минут
    WORKOUT_STATS_TTL = 300  # 5 минут
    DAILY_NUTRITION_TTL = 60  # 1 минута
    GENERATED_WORKOUT_TTL = 3600  # 1 час
    USER_DATA_TTL = 60  # 1 минута


async def get_redis() -> Redis | None:
    """Получить Redis клиент. Возвращает None если Redis недоступен."""
    global _redis_pool, _redis_client
    
    settings = get_settings()
    
    if not settings.redis_url:
        return None
    
    if _redis_client is not None:
        try:
            await _redis_client.ping()
            return _redis_client
        except RedisError:
            _redis_client = None
            _redis_pool = None
    
    try:
        _redis_pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=10,
            decode_responses=True
        )
        _redis_client = Redis(connection_pool=_redis_pool)
        await _redis_client.ping()
        logger.info("Redis connection established")
        return _redis_client
    except RedisError as e:
        logger.warning(f"Redis unavailable, caching disabled: {e}")
        _redis_client = None
        _redis_pool = None
        return None


async def close_redis() -> None:
    """Закрыть Redis соединение."""
    global _redis_client, _redis_pool
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
    
    logger.info("Redis connection closed")


def make_cache_key(*args: str) -> str:
    """Создать ключ кэша из аргументов."""
    key_data = ":".join(str(arg) for arg in args)
    return f"fitness:{key_data}"


def hash_dict(data: dict) -> str:
    """Создать хэш словаря для использования в ключе кэша."""
    sorted_json = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(sorted_json.encode()).hexdigest()[:12]


async def cache_get(key: str) -> dict | list | None:
    """
    Получить значение из кэша.
    
    Returns:
        Закэшированные данные или None если не найдено/ошибка
    """
    redis = await get_redis()
    if not redis:
        return None
    
    try:
        value = await redis.get(key)
        if value:
            return json.loads(value)
        return None
    except (RedisError, json.JSONDecodeError) as e:
        logger.warning(f"Cache get error for key {key}: {e}")
        return None


async def cache_set(key: str, value: dict | list, ttl: int) -> bool:
    """
    Сохранить значение в кэш.
    
    Args:
        key: Ключ кэша
        value: Данные для сохранения
        ttl: Время жизни в секундах
    
    Returns:
        True если сохранено успешно
    """
    redis = await get_redis()
    if not redis:
        return False
    
    try:
        await redis.setex(key, ttl, json.dumps(value, default=str))
        return True
    except (RedisError, TypeError) as e:
        logger.warning(f"Cache set error for key {key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """Удалить ключ из кэша."""
    redis = await get_redis()
    if not redis:
        return False
    
    try:
        await redis.delete(key)
        return True
    except RedisError as e:
        logger.warning(f"Cache delete error for key {key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    Удалить все ключи по паттерну.
    
    Returns:
        Количество удалённых ключей
    """
    redis = await get_redis()
    if not redis:
        return 0
    
    try:
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)
        
        if keys:
            return await redis.delete(*keys)
        return 0
    except RedisError as e:
        logger.warning(f"Cache delete pattern error for {pattern}: {e}")
        return 0


async def invalidate_user_cache(user_id: str) -> None:
    """Инвалидировать весь кэш пользователя."""
    await cache_delete_pattern(f"fitness:user:{user_id}:*")
