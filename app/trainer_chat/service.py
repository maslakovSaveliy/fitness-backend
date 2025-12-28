import logging
from datetime import datetime
from openai import AsyncOpenAI
from app.config import get_settings
from app.db import supabase_client

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = logging.getLogger(__name__)


async def create_session(user: dict, original_workout_text: str | None) -> dict:
	session = {
		"user_id": user["id"],
		"status": "active",
		"original_workout_text": original_workout_text,
	}
	result = await supabase_client.insert("trainer_chat_sessions", session)
	return result[0] if result else None


async def get_session(session_id: str, user_id: str) -> dict | None:
	return await supabase_client.get_one(
		"trainer_chat_sessions",
		{"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
	)


async def list_messages(session_id: str) -> list[dict]:
	return await supabase_client.get(
		"trainer_chat_messages",
		{"session_id": f"eq.{session_id}", "order": "created_at.asc", "limit": "200"},
	)


async def add_message(session_id: str, role: str, content: str) -> dict | None:
	payload = {
		"session_id": session_id,
		"role": role,
		"content": content,
		"created_at": datetime.utcnow().isoformat(),
	}
	result = await supabase_client.insert("trainer_chat_messages", payload)
	return result[0] if result else None


async def _get_recent_workouts(user_id: str) -> list[dict]:
	return await supabase_client.get(
		"workouts",
		{"user_id": f"eq.{user_id}", "order": "date.desc", "limit": "5"},
	)


async def _get_recent_meals(user_id: str) -> list[dict]:
	return await supabase_client.get(
		"meals",
		{"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "3"},
	)


def _format_recent_workouts(workouts: list[dict]) -> str:
	if not workouts:
		return "История тренировок пуста.\n"
	lines: list[str] = ["Последние тренировки:"]
	for idx, w in enumerate(workouts[:3], 1):
		date = w.get("date", "неизвестно")
		workout_type = w.get("workout_type", "неизвестно")
		calories = w.get("calories_burned", "н/д")
		details = (w.get("details") or "")[:200]
		rating = w.get("rating")
		rating_text = f"{rating}/5" if rating else "—"
		lines.append(f"{idx}. {date}: {workout_type} (калории: {calories}, оценка: {rating_text})")
		lines.append(f"   {details}")
	return "\n".join(lines) + "\n"


def _format_recent_meals(meals: list[dict]) -> str:
	if not meals:
		return "История питания пуста.\n"
	lines: list[str] = ["Последние приёмы пищи:"]
	for idx, m in enumerate(meals[:3], 1):
		date = m.get("date", "неизвестно")
		desc = (m.get("description") or "")[:160]
		calories = m.get("calories", "н/д")
		proteins = m.get("proteins", "н/д")
		fats = m.get("fats", "н/д")
		carbs = m.get("carbs", "н/д")
		lines.append(f"{idx}. {date}: {desc}")
		lines.append(f"   КБЖУ: {calories} ккал, Б:{proteins}г, Ж:{fats}г, У:{carbs}г")
	return "\n".join(lines) + "\n"


def _build_user_context(user: dict, workouts: list[dict], meals: list[dict], original_workout: str | None) -> str:
	return "\n".join(
		[
			"Характеристики пользователя:",
			f"- Цель: {user.get('goal', 'не указано')}",
			f"- Уровень: {user.get('level', 'не указано')}",
			f"- Ограничения по здоровью: {user.get('health_issues', 'нет')}",
			f"- Место занятий: {user.get('location', 'не указано')}",
			f"- Частота тренировок: {user.get('workouts_per_week', 'не указано')} раз в неделю",
			f"- Время на тренировку: {user.get('workout_duration', 'не указано')}",
			f"- Оборудование: {user.get('equipment', 'не указано')}",
			f"- Формат тренировок: {user.get('workout_formats', 'не указано')}",
			f"- Рост: {user.get('height', 'не указано')} см",
			f"- Вес: {user.get('weight', 'не указано')} кг",
			f"- Возраст: {user.get('age', 'не указано')}",
			f"- Пол: {user.get('gender', 'не указано')}",
			"",
			_format_recent_workouts(workouts),
			_format_recent_meals(meals),
			"Текущая тренировка для обсуждения:",
			original_workout or "Не задана",
		]
	)


def _build_system_prompt(user_context: str) -> str:
	return (
		"Ты персональный фитнес-тренер. Веди диалог с пользователем о корректировке тренировки.\n\n"
		f"{user_context}\n\n"
		"Правила:\n"
		"- Отвечай по-русски, кратко и конкретно (до 150 слов).\n"
		"- Предлагай конкретные замены упражнений/веса/подходов/повторов и объясняй технику.\n"
		"- Учитывай уровень, оборудование, ограничения и историю.\n"
		"- Если запрос пользователя опасен для здоровья — предложи безопасную альтернативу.\n"
	)


async def send_trainer_message(session: dict, user: dict, text: str) -> str:
	if not settings.openai_api_key:
		logger.error("openai_api_key_is_missing")
		raise RuntimeError("OpenAI API key is missing")

	await add_message(session["id"], "user", text)
	messages = await list_messages(session["id"])

	recent_workouts = await _get_recent_workouts(user["id"])
	recent_meals = await _get_recent_meals(user["id"])
	user_context = _build_user_context(user, recent_workouts, recent_meals, session.get("original_workout_text"))
	system_prompt = _build_system_prompt(user_context)

	chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
	for msg in messages:
		role = msg.get("role")
		content = msg.get("content") or ""
		if role in ("user", "assistant"):
			chat_messages.append({"role": role, "content": content})

	logger.info(
		"trainer_chat_message_request",
		extra={"session_id": session["id"], "user_id": user["id"]},
	)

	response = await client.chat.completions.create(
		model="gpt-4o",
		messages=chat_messages,
		temperature=0.4,
		max_tokens=450,
	)
	assistant_text = (response.choices[0].message.content or "").strip()
	if not assistant_text:
		raise RuntimeError("AI returned empty trainer response")

	await add_message(session["id"], "assistant", assistant_text)
	return assistant_text


async def finish_trainer_chat(session: dict, user: dict) -> str:
	if not settings.openai_api_key:
		logger.error("openai_api_key_is_missing")
		raise RuntimeError("OpenAI API key is missing")

	messages = await list_messages(session["id"])
	recent_workouts = await _get_recent_workouts(user["id"])
	recent_meals = await _get_recent_meals(user["id"])
	user_context = _build_user_context(user, recent_workouts, recent_meals, session.get("original_workout_text"))

	system_prompt = (
		"Ты персональный фитнес-тренер. На основе диалога создай обновлённую тренировку.\n"
		"Отвечай строго в формате:\n"
		"Совет дня: ...\n\n"
		"План тренировки на сегодня: ...\n\n"
		"1. ...\nподходы × повторения — вес\n*комментарий*\n\n"
		"Последнее упражнение — кардио или заминка.\n\n"
		f"{user_context}\n"
	)

	chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
	for msg in messages:
		role = msg.get("role")
		content = msg.get("content") or ""
		if role in ("user", "assistant"):
			chat_messages.append({"role": role, "content": content})

	chat_messages.append(
		{
			"role": "user",
			"content": (
				"Сформируй итоговую тренировку, учитывая все пожелания выше. "
				"Не добавляй лишних объяснений вне структуры плана."
			),
		}
	)

	logger.info("trainer_chat_finish_request", extra={"session_id": session["id"], "user_id": user["id"]})

	response = await client.chat.completions.create(
		model="gpt-4o",
		messages=chat_messages,
		temperature=0.4,
		max_tokens=1200,
	)
	updated_workout_text = (response.choices[0].message.content or "").strip()
	if not updated_workout_text:
		raise RuntimeError("AI returned empty updated workout")

	await supabase_client.update(
		"trainer_chat_sessions",
		{"id": f"eq.{session['id']}", "user_id": f"eq.{user['id']}"},
		{"status": "finished", "updated_workout_text": updated_workout_text},
	)

	return updated_workout_text


async def revert_trainer_chat(session: dict, user: dict) -> str:
	original = session.get("original_workout_text") or ""
	await supabase_client.update(
		"trainer_chat_sessions",
		{"id": f"eq.{session['id']}", "user_id": f"eq.{user['id']}"},
		{"status": "reverted"},
	)
	return original


