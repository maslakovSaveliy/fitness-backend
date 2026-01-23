from pydantic import BaseModel
from typing import Optional


class TelegramAuthRequest(BaseModel):
    init_data: str


class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = None
    photo_url: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_paid: bool = False
    is_pro: bool = False
    has_profile: bool = False
    onboarding_completed: bool = False


TokenResponse.model_rebuild()

