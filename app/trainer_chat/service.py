import logging
from datetime import datetime
from openai import AsyncOpenAI
from app.config import get_settings
from app.db import supabase_client
from app.ai import ai_service
from app.workouts.schemas import WorkoutResponse, WorkoutStructured
from app.workouts.service import _format_workout_text, get_workout_by_id

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = logging.getLogger(__name__)

def _details_to_response_fields(details_value: object) -> tuple[str, object | None]:
	# details в проде jsonb: либо строка (legacy), либо объект (структура 1-в-1).
	if isinstance(details_value, str):
		return details_value, None
	if isinstance(details_value, dict):
		try:
			structured = WorkoutStructured.model_validate(details_value)
			return _format_workout_text(structured), details_value
		except Exception:
			try:
				import json as _json

				return _json.dumps(details_value, ensure_ascii=False), None
			except Exception:
				return str(details_value), None
	return "", None


async def _get_workout_counts(user_id: str) -> tuple[int, int]:
	# total completed
	all_workouts = await supabase_client.get(
		"workouts",
		{"user_id": f"eq.{user_id}", "status": "eq.completed", "select": "id,date"},
	)
	total = len(all_workouts) if all_workouts else 0

	month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
	month_start_iso = month_start.isoformat()[:10]
	month_workouts = await supabase_client.get(
		"workouts",
		{
			"user_id": f"eq.{user_id}",
			"status": "eq.completed",
			"date": f"gte.{month_start_iso}",
			"select": "id",
		},
	)
	month_total = len(month_workouts) if month_workouts else 0
	return total, month_total


async def create_session(user: dict, workout_id: str) -> tuple[dict | None, str | None]:
	workout = await get_workout_by_id(workout_id, user["id"])
	if not workout:
		return None, None
	if workout.get("status") != "draft":
		return None, None

	details_value = workout.get("details")
	original_text, _ = _details_to_response_fields(details_value)

	session_payload = {
		"user_id": user["id"],
		"status": "active",
		"workout_id": workout_id,
		"original_workout_text": original_text,
		"original_workout_details": details_value,
		"updated_at": datetime.utcnow().isoformat(),
	}
	created = await supabase_client.insert("trainer_chat_sessions", session_payload)
	session = created[0] if created else None
	if not session:
		return None, None

	recent_workouts = await _get_recent_workouts(user["id"])
	recent_meals = await _get_recent_meals(user["id"])

	workouts_info = _format_recent_workouts(recent_workouts)
	meals_info = _format_recent_meals(recent_meals)

	greeting = (
		"Привет! Я твой персональный тренер и помогу скорректировать тренировку.\n\n"
		"Я вижу твою историю тренировок и питания.\n\n"
		f"{workouts_info}\n\n{meals_info}\n\n"
		"Напиши, что поменять (упражнения/вес/подходы/повторы/техника/самочувствие).\n"
		"Когда закончишь — нажми «Готово», и я перепишу тренировку."
	).strip()

	# Сохраняем greeting как первое сообщение ассистента (как в боте).
	await add_message(session["id"], "assistant", greeting)

	return session, greeting


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
		details_value = w.get("details")
		details_text = _details_to_response_fields(details_value)[0]
		details = details_text[:200]
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
	original_workout_text = session.get("original_workout_text")
	if not isinstance(original_workout_text, str) or not original_workout_text.strip():
		original_details = session.get("original_workout_details")
		original_workout_text = _details_to_response_fields(original_details)[0]

	user_context = _build_user_context(user, recent_workouts, recent_meals, original_workout_text)
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


async def finish_trainer_chat(session: dict, user: dict) -> WorkoutResponse | None:
	if not settings.openai_api_key:
		logger.error("openai_api_key_is_missing")
		raise RuntimeError("OpenAI API key is missing")

	messages = await list_messages(session["id"])
	recent_workouts = await _get_recent_workouts(user["id"])
	recent_meals = await _get_recent_meals(user["id"])
	workout_id = session.get("workout_id")
	if not isinstance(workout_id, str) or not workout_id.strip():
		return None

	workout = await get_workout_by_id(workout_id, user["id"])
	if not workout or workout.get("status") != "draft":
		return None

	original_details = session.get("original_workout_details") or workout.get("details")
	original_text = _details_to_response_fields(original_details)[0]

	# Определяем “целевую” группу мышц: берём из generation_context (если есть), иначе из structured.
	target_muscle_group: str | None = None
	ctx = workout.get("generation_context")
	if isinstance(ctx, dict):
		tmg = ctx.get("target_muscle_group")
		if isinstance(tmg, str) and tmg.strip():
			target_muscle_group = tmg.strip()
	if not target_muscle_group and isinstance(workout.get("details"), dict):
		try:
			structured = WorkoutStructured.model_validate(workout.get("details"))
			if structured.muscle_groups:
				target_muscle_group = ", ".join(structured.muscle_groups[:2])
		except Exception:
			target_muscle_group = None
	if not target_muscle_group:
		target_muscle_group = "Тренировка"

	user_context = _build_user_context(user, recent_workouts, recent_meals, original_text)

	# Финальная генерация: возвращаем structured JSON как для WorkoutPage (version/title/muscle_groups/exercises + calories_burned).
	system_prompt = (
		"Ты персональный фитнес-тренер. На основе диалога перепиши тренировку.\n"
		"Верни СТРОГО валидный JSON-объект без Markdown и без пояснений.\n\n"
		f"{user_context}\n\n"
		"ТРЕБОВАНИЯ К JSON:\n"
		"{\n"
		'  \"version\": 1,\n'
		'  \"title\": \"Короткий заголовок тренировки\",\n'
		f'  \"muscle_groups\": [\"{target_muscle_group}\"],\n'
		"  \"exercises\": [\n"
		"    {\"name\": \"Название упражнения\", \"weight_kg\": 4, \"sets\": 3, \"reps\": 12}\n"
		"  ],\n"
		"  \"calories_burned\": 320\n"
		"}\n\n"
		"ОГРАНИЧЕНИЯ:\n"
		f"- muscle_groups: 1–2 группы мышц, соответствующие тренировке: {target_muscle_group}\n"
		"- exercises: 5–8 упражнений\n"
		"- sets: 2–6\n"
		"- reps: одно из значений: 5, 8, 10, 12, 15\n"
		"- weight_kg: одно из значений: 2, 4, 6, 8, 10, 12, 16, 20, 25, 30, 40, 50 (если вес не нужен — 0)\n"
		"- calories_burned: целое число\n"
	)

	chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
	for msg in messages:
		role = msg.get("role")
		content = (msg.get("content") or "").strip()
		if role in ("user", "assistant") and content:
			chat_messages.append({"role": role, "content": content})

	chat_messages.append(
		{
			"role": "user",
			"content": (
				"Сформируй итоговую тренировку в формате JSON, учитывая все пожелания из диалога. "
				"Тренировка должна быть практичной и выполнимой с учётом уровня/оборудования/ограничений."
			),
		}
	)

	logger.info("trainer_chat_finish_request", extra={"session_id": session["id"], "user_id": user["id"]})

	try:
		response = await client.chat.completions.create(
			model="gpt-4o",
			messages=chat_messages,
			temperature=0.4,
			max_tokens=1100,
			response_format={"type": "json_object"},
		)
	except TypeError:
		response = await client.chat.completions.create(
			model="gpt-4o",
			messages=chat_messages,
			temperature=0.4,
			max_tokens=1100,
		)

	raw = (response.choices[0].message.content or "").strip()
	parsed = ai_service._extract_json_object(raw)
	if not parsed:
		raise RuntimeError("AI returned invalid JSON for updated workout")

	normalized = ai_service._normalize_structured_workout(parsed, fallback_muscle_group=target_muscle_group)
	calories_raw = normalized.get("calories_burned")
	calories_burned: int | None = None
	if isinstance(calories_raw, int) and calories_raw > 0:
		calories_burned = calories_raw
	if isinstance(calories_raw, float):
		calories_burned = int(calories_raw)

	structured = WorkoutStructured.model_validate(normalized)

	update_payload: dict[str, object] = {
		"details": structured.model_dump(),
		"updated_at": datetime.utcnow().isoformat(),
	}
	if calories_burned is not None:
		update_payload["calories_burned"] = calories_burned

	updated_rows = await supabase_client.update(
		"workouts",
		{"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.draft"},
		update_payload,
	)
	updated_workout = updated_rows[0] if updated_rows else None
	if not updated_workout:
		return None

	await supabase_client.update(
		"trainer_chat_sessions",
		{"id": f"eq.{session['id']}", "user_id": f"eq.{user['id']}"},
		{
			"status": "finished",
			"updated_workout_details": structured.model_dump(),
			"updated_workout_text": _format_workout_text(structured),
			"updated_at": datetime.utcnow().isoformat(),
		},
	)

	details_text, details_structured = _details_to_response_fields(updated_workout.get("details"))
	return WorkoutResponse(
		id=updated_workout["id"],
		user_id=updated_workout["user_id"],
		date=updated_workout["date"],
		workout_type=updated_workout["workout_type"],
		details=details_text,
		details_structured=details_structured,
		calories_burned=updated_workout.get("calories_burned"),
		status=updated_workout.get("status"),
		rating=updated_workout.get("rating"),
		comment=updated_workout.get("comment"),
		created_at=updated_workout.get("created_at"),
	)


async def revert_trainer_chat(session: dict, user: dict) -> WorkoutResponse | None:
	workout_id = session.get("workout_id")
	if not isinstance(workout_id, str) or not workout_id.strip():
		return None

	original_details = session.get("original_workout_details")
	if original_details is None:
		return None

	updated_rows = await supabase_client.update(
		"workouts",
		{"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.draft"},
		{"details": original_details, "updated_at": datetime.utcnow().isoformat()},
	)
	updated_workout = updated_rows[0] if updated_rows else None
	if not updated_workout:
		return None

	await supabase_client.update(
		"trainer_chat_sessions",
		{"id": f"eq.{session['id']}", "user_id": f"eq.{user['id']}"},
		{"status": "reverted", "updated_at": datetime.utcnow().isoformat()},
	)

	details_text, details_structured = _details_to_response_fields(updated_workout.get("details"))
	return WorkoutResponse(
		id=updated_workout["id"],
		user_id=updated_workout["user_id"],
		date=updated_workout["date"],
		workout_type=updated_workout["workout_type"],
		details=details_text,
		details_structured=details_structured,
		calories_burned=updated_workout.get("calories_burned"),
		status=updated_workout.get("status"),
		rating=updated_workout.get("rating"),
		comment=updated_workout.get("comment"),
		created_at=updated_workout.get("created_at"),
	)


