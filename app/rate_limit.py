from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import get_settings

settings = get_settings()


def get_user_identifier(request: Request) -> str:
    """
    Получить идентификатор пользователя для rate limiting.
    Использует user_id из JWT если доступен, иначе IP.
    """
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"
    
    return get_remote_address(request)


limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    storage_uri=settings.redis_url if settings.redis_url else "memory://",
    strategy="fixed-window"
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Обработчик превышения лимита запросов."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Слишком много запросов. Пожалуйста, подождите.",
            "retry_after": exc.detail
        }
    )


def get_ai_rate_limit() -> str:
    """Получить строку лимита для AI эндпоинтов."""
    return f"{settings.rate_limit_ai_per_minute}/minute"
