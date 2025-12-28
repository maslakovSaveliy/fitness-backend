from datetime import datetime
from app.db import supabase_client
from app.telegram import telegram_service


async def create_broadcast(created_by: str, text: str, audience: str) -> dict | None:
	payload = {
		"created_by": created_by,
		"text": text,
		"audience": audience,
		"status": "created",
		"created_at": datetime.utcnow().isoformat(),
	}
	result = await supabase_client.insert("broadcasts", payload)
	return result[0] if result else None


async def list_audience_users(audience: str) -> list[dict]:
	if audience == "paid":
		return await supabase_client.get("users", {"is_paid": "eq.true", "select": "id,telegram_id", "limit": "10000"})
	if audience == "unpaid":
		return await supabase_client.get("users", {"is_paid": "eq.false", "select": "id,telegram_id", "limit": "10000"})
	return await supabase_client.get("users", {"select": "id,telegram_id", "limit": "10000"})


async def send_broadcast(broadcast: dict) -> int:
	users = await list_audience_users(broadcast.get("audience") or "all")
	to_send: list[tuple[int, str]] = []
	for u in users:
		telegram_id = u.get("telegram_id")
		if isinstance(telegram_id, int):
			to_send.append((telegram_id, broadcast["text"]))

	await supabase_client.update("broadcasts", {"id": f"eq.{broadcast['id']}"}, {"status": "sending"})
	await telegram_service.send_many_messages(to_send)
	await supabase_client.update("broadcasts", {"id": f"eq.{broadcast['id']}"}, {"status": "sent"})
	return len(to_send)


