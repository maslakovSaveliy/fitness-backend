import logging
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.telegram import telegram_service
from .service import get_inactive_paid_users, get_week_ago_iso
from app.users.service import deactivate_expired_subscriptions

logger = logging.getLogger(__name__)

REMINDER_PHRASES = [
	"Ты заслужил это тело",
	"Дисциплина — это мост между целями и достижениями — Джим Рон",
	"Весь прогресс происходит за пределами зоны комфорта — Михал Джоан Бобак",
	"Единственный с кем ты соревнуешься это ты, но вчерашний",
]


async def send_inactivity_reminders() -> None:
	week_ago = get_week_ago_iso()
	users = await get_inactive_paid_users(week_ago)
	to_send: list[tuple[int, str]] = []

	for u in users:
		telegram_id = u.get("telegram_id")
		if not isinstance(telegram_id, int):
			continue
		phrase = random.choice(REMINDER_PHRASES)
		text = f"{phrase}\n\nНе забывай про тренировки и питание. Я всегда на связи."
		to_send.append((telegram_id, text))

	if to_send:
		logger.info("sending_inactivity_reminders", extra={"count": len(to_send)})
		await telegram_service.send_many_messages(to_send)


async def daily_deactivate_expired() -> None:
	updated = await deactivate_expired_subscriptions()
	if updated:
		logger.info("deactivated_expired_subscriptions", extra={"count": updated})


def start_scheduler() -> AsyncIOScheduler:
	scheduler = AsyncIOScheduler()
	scheduler.add_job(send_inactivity_reminders, "interval", days=14)
	scheduler.add_job(daily_deactivate_expired, "interval", days=1)
	scheduler.start()
	return scheduler


