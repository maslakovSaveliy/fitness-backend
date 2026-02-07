from pydantic import BaseModel


class PromoValidateRequest(BaseModel):
    code: str


class PromoValidateResponse(BaseModel):
    is_valid: bool
    message: str


class PromoCodeCreate(BaseModel):
    code: str
    description: str = ""


class PromoCodeResponse(BaseModel):
    id: str
    code: str
    description: str | None
    is_active: bool
    created_at: str


class PromoEventCount(BaseModel):
    start: int = 0
    trial: int = 0
    subscription: int = 0


class PromoStatItem(BaseModel):
    promo_code: PromoCodeResponse
    events: PromoEventCount


class PromoStatsResponse(BaseModel):
    items: list[PromoStatItem]
