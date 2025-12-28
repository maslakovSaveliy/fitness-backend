from datetime import datetime, timedelta
from app.db import supabase_client
from .schemas import ReminderSettingsUpdateRequest


async def get_or_create_user_reminder(user_id: str) -> dict:
	existing = await supabase_client.get_one("user_reminders", {"user_id": f"eq.{user_id}"})
	if existing:
		return existing
	result = await supabase_client.insert(
		"user_reminders",
		{"user_id": user_id, "enabled": True, "timezone": None},
	)
	return result[0] if result else {"id": "", "user_id": user_id, "enabled": True, "timezone": None}


async def update_user_reminder(user_id: str, data: ReminderSettingsUpdateRequest) -> dict:
	update_data = data.model_dump(exclude_none=True)
	if not update_data:
		return await get_or_create_user_reminder(user_id)
	result = await supabase_client.update(
		"user_reminders",
		{"user_id": f"eq.{user_id}"},
		update_data,
	)
	return result[0] if result else await get_or_create_user_reminder(user_id)


async def get_disabled_user_ids() -> set[str]:
	rows = await supabase_client.get("user_reminders", {"enabled": "eq.false", "select": "user_id", "limit": "10000"})
	return {r["user_id"] for r in rows if isinstance(r.get("user_id"), str)}


async def get_inactive_paid_users(week_ago_iso: str) -> list[dict]:
	return await supabase_client.get(
		"users",
		{
			"last_active_at": f"lt.{week_ago_iso}",
			"is_paid": "eq.true",
			"select": "id,telegram_id",
			"limit": "10000",
		},
	)


def get_week_ago_iso() -> str:
	return (datetime.utcnow() - timedelta(days=7)).isoformat()


