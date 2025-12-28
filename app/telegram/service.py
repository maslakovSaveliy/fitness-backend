import asyncio
import logging
import httpx
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class TelegramService:
	def __init__(self) -> None:
		self._token = settings.telegram_bot_token
		self._api_url = f"https://api.telegram.org/bot{self._token}"

	async def send_message(self, chat_id: int, text: str) -> None:
		if not self._token:
			raise RuntimeError("telegram_bot_token is missing")

		async with httpx.AsyncClient(timeout=10.0) as client:
			resp = await client.post(
				f"{self._api_url}/sendMessage",
				json={
					"chat_id": chat_id,
					"text": text,
					"disable_web_page_preview": True,
				},
			)
			resp.raise_for_status()

	async def send_many_messages(self, items: list[tuple[int, str]]) -> None:
		for chat_id, text in items:
			try:
				await self.send_message(chat_id, text)
			except Exception:
				logger.exception("telegram_send_failed", extra={"chat_id": chat_id})
			# ~20 msg/sec
			await asyncio.sleep(0.05)


telegram_service = TelegramService()


