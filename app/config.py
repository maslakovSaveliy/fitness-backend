from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str
    
    # Telegram
    telegram_bot_token: str
    
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 дней
    
    # OpenAI
    openai_api_key: str
    
    # Redis (optional)
    redis_url: str | None = None
    
    # Sentry (optional)
    sentry_dsn: str | None = None
    
    # App settings
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False
    
    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_ai_per_minute: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
