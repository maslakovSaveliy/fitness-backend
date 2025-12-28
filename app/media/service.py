import logging
import os
import tempfile
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = logging.getLogger(__name__)


async def transcribe_audio(file_bytes: bytes, filename: str) -> str:
	if not settings.openai_api_key:
		logger.error("openai_api_key_is_missing")
		raise RuntimeError("OpenAI API key is missing")

	suffix = os.path.splitext(filename)[1] or ".wav"
	with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
		tmp.write(file_bytes)
		tmp_path = tmp.name

	try:
		with open(tmp_path, "rb") as f:
			result = await client.audio.transcriptions.create(
				model="whisper-1",
				file=f,
				response_format="text",
			)
		text = str(result).strip()
		if not text:
			raise RuntimeError("Empty transcription")
		return text
	finally:
		try:
			os.remove(tmp_path)
		except Exception:
			pass


