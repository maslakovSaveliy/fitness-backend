from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user, get_current_admin_user
from .schemas import (
    PromoValidateRequest,
    PromoValidateResponse,
    PromoCodeCreate,
    PromoCodeResponse,
    PromoStatsResponse,
    PromoStatItem,
    PromoEventCount,
)
from . import service

router = APIRouter(prefix="/promo", tags=["promo"])


@router.post("/validate", response_model=PromoValidateResponse)
async def validate_promo(
    body: PromoValidateRequest,
    user: dict = Depends(get_current_user),
):
    """Валидирует промокод и привязывает к пользователю. Записывает событие 'start'."""
    if user.get("promo_code_id"):
        return PromoValidateResponse(is_valid=True, message="Промокод уже применён")

    code_row = await service.get_promo_code_by_code(body.code.strip().upper())
    if not code_row:
        return PromoValidateResponse(is_valid=False, message="Промокод не найден или неактивен")

    await service.apply_promo_to_user(user["id"], code_row["id"])
    return PromoValidateResponse(is_valid=True, message="Промокод активирован! Trial доступен в боте")


@router.get("/codes", response_model=list[PromoCodeResponse])
async def list_codes(user: dict = Depends(get_current_admin_user)):
    """Список всех промокодов (только админ)."""
    rows = await service.list_promo_codes()
    return [
        PromoCodeResponse(
            id=r["id"],
            code=r["code"],
            description=r.get("description"),
            is_active=r.get("is_active", True),
            created_at=r.get("created_at", ""),
        )
        for r in rows
    ]


@router.post("/codes", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_code(
    body: PromoCodeCreate,
    user: dict = Depends(get_current_admin_user),
):
    """Создание нового промокода (только админ)."""
    r = await service.create_promo_code(body.code.strip().upper(), body.description)
    return PromoCodeResponse(
        id=r["id"],
        code=r["code"],
        description=r.get("description"),
        is_active=r.get("is_active", True),
        created_at=r.get("created_at", ""),
    )


@router.get("/stats", response_model=PromoStatsResponse)
async def promo_stats(user: dict = Depends(get_current_admin_user)):
    """Статистика по промокодам: сколько start / trial / subscription (только админ)."""
    raw = await service.get_promo_stats()
    items: list[PromoStatItem] = []
    for entry in raw:
        pc = entry["promo_code"]
        ev = entry["events"]
        items.append(
            PromoStatItem(
                promo_code=PromoCodeResponse(
                    id=pc["id"],
                    code=pc["code"],
                    description=pc.get("description"),
                    is_active=pc.get("is_active", True),
                    created_at=pc.get("created_at", ""),
                ),
                events=PromoEventCount(
                    start=ev.get("start", 0),
                    trial=ev.get("trial", 0),
                    subscription=ev.get("subscription", 0),
                ),
            )
        )
    return PromoStatsResponse(items=items)
