import logging
from app.db import supabase_client

logger = logging.getLogger(__name__)


async def get_promo_code_by_code(code: str) -> dict | None:
    """Ищет промокод по строковому значению."""
    return await supabase_client.get_one(
        "promo_codes",
        {"code": f"eq.{code}", "is_active": "eq.true"},
    )


async def apply_promo_to_user(user_id: str, promo_code_id: str) -> None:
    """Привязывает промокод к пользователю и записывает событие 'start'."""
    await supabase_client.update(
        "users",
        {"id": f"eq.{user_id}"},
        {"promo_code_id": promo_code_id},
    )
    await _record_event(promo_code_id, user_id, "start")


async def list_promo_codes() -> list[dict]:
    """Возвращает все промокоды."""
    return await supabase_client.get(
        "promo_codes",
        {"order": "created_at.desc"},
    )


async def create_promo_code(code: str, description: str) -> dict:
    """Создаёт новый промокод."""
    rows = await supabase_client.insert(
        "promo_codes",
        {"code": code, "description": description},
    )
    return rows[0]


async def get_promo_stats() -> list[dict]:
    """Собирает статистику по каждому промокоду: кол-во start / trial / subscription."""
    codes = await supabase_client.get("promo_codes", {"order": "created_at.desc"})
    result: list[dict] = []

    for code_row in codes:
        code_id = code_row["id"]
        events = await supabase_client.get(
            "promo_events",
            {"promo_code_id": f"eq.{code_id}"},
        )
        counts = {"start": 0, "trial": 0, "subscription": 0}
        for ev in events:
            et = ev.get("event_type", "")
            if et in counts:
                counts[et] += 1

        result.append({"promo_code": code_row, "events": counts})

    return result


async def _record_event(promo_code_id: str, user_id: str, event_type: str) -> None:
    """Записывает promo event. UNIQUE constraint предотвращает дубликаты."""
    try:
        headers_override = {"Prefer": "return=representation,resolution=ignore-duplicates"}
        # Supabase upsert-like via ignore-duplicates
        import httpx
        from app.db.client import SUPABASE_API, get_supabase_headers, TIMEOUT_CONFIG
        headers = {**get_supabase_headers(), **headers_override}
        async with httpx.AsyncClient(timeout=TIMEOUT_CONFIG) as client:
            resp = await client.post(
                f"{SUPABASE_API}/promo_events",
                headers=headers,
                json=[{
                    "promo_code_id": promo_code_id,
                    "user_id": user_id,
                    "event_type": event_type,
                }],
            )
            if resp.status_code not in (200, 201, 409):
                logger.error("promo_events insert error: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("record_promo_event error: %s", e)
