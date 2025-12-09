from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.rate_limit import limiter
from app.cache import close_redis
from app.db import supabase_client
from app.auth import auth_router
from app.users import users_router
from app.workouts import workouts_router
from app.nutrition import nutrition_router

settings = get_settings()

setup_logging(
    level=settings.log_level,  # type: ignore
    json_format=settings.log_json
)
logger = get_logger(__name__)

if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.httpx import HttpxIntegration
    
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            HttpxIntegration(),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment="production" if not settings.debug else "development",
        send_default_pii=False
    )
    logger.info("Sentry monitoring initialized")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управление жизненным циклом приложения."""
    logger.info("Application starting up...")
    yield
    logger.info("Application shutting down...")
    await supabase_client.close()
    await close_redis()
    logger.info("Cleanup completed")


app = FastAPI(
    title="Fitness Mini App API",
    description="Backend API for Fitness Telegram Mini App",
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# TODO: В продакшене заменить "*" на реальные домены:
# allow_origins=["https://your-app.telegram.org", "https://your-domain.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(workouts_router)
app.include_router(nutrition_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Проверка здоровья сервиса."""
    return {"status": "ok"}


@app.get("/health/detailed")
async def detailed_health_check() -> dict[str, dict[str, str]]:
    """Детальная проверка здоровья с проверкой зависимостей."""
    from app.cache import get_redis
    
    status: dict[str, dict[str, str]] = {
        "api": {"status": "ok"},
        "database": {"status": "unknown"},
        "cache": {"status": "disabled"}
    }
    
    try:
        await supabase_client.get("users", {"limit": "1"})
        status["database"] = {"status": "ok"}
    except Exception as e:
        status["database"] = {"status": "error", "message": str(e)}
    
    redis = await get_redis()
    if redis:
        try:
            await redis.ping()
            status["cache"] = {"status": "ok"}
        except Exception as e:
            status["cache"] = {"status": "error", "message": str(e)}
    
    return status


@app.get("/")
async def root() -> dict[str, str]:
    """Корневой эндпоинт с информацией об API."""
    return {
        "app": "Fitness Mini App API",
        "version": "1.0.0",
        "docs": "/docs"
    }
