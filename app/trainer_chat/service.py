import logging
from collections.abc import AsyncGenerator
from datetime import datetime

from app.config import get_settings
from app.db import supabase_client
from app.ai import ai_service
from app.ai.prompts import TRAINER_CHAT_WORKOUT_SYSTEM
from app.workouts.schemas import WorkoutResponse, WorkoutStructured
from app.workouts.service import _format_workout_text, get_workout_by_id

settings = get_settings()
logger = logging.getLogger(__name__)


def _details_to_response_fields(details_value: object) -> tuple[str, object | None]:
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


# ------------------------------------------------------------------
# Streaming chat
# ------------------------------------------------------------------

async def send_trainer_message_stream(
    session: dict,
    user: dict,
    text: str,
) -> AsyncGenerator[str, None]:
    """Yield text chunks from the trainer AI response, then save the full message."""
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is missing")

    await add_message(session["id"], "user", text)
    messages = await list_messages(session["id"])

    chat_messages = _build_chat_messages(session, user, messages)

    logger.info("trainer_chat_stream", extra={"session_id": session["id"], "user_id": user["id"]})

    full_text = ""
    async for chunk in ai_service.stream_chat_completion(chat_messages, temperature=0.4, max_tokens=450):
        full_text += chunk
        yield chunk

    if full_text.strip():
        await add_message(session["id"], "assistant", full_text.strip())


async def send_trainer_message(session: dict, user: dict, text: str) -> str:
    """Non-streaming fallback — collects all chunks into a single string."""
    parts: list[str] = []
    async for chunk in send_trainer_message_stream(session, user, text):
        parts.append(chunk)
    return "".join(parts)


# ------------------------------------------------------------------
# Finish / revert
# ------------------------------------------------------------------

async def finish_trainer_chat(session: dict, user: dict) -> WorkoutResponse | None:
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is missing")

    messages = await list_messages(session["id"])
    workout_id = session.get("workout_id")
    if not isinstance(workout_id, str) or not workout_id.strip():
        return None

    workout = await get_workout_by_id(workout_id, user["id"])
    if not workout or workout.get("status") != "draft":
        return None

    original_details = session.get("original_workout_details") or workout.get("details")
    original_text = _details_to_response_fields(original_details)[0]

    target_muscle_group = _resolve_target_muscle_group(workout)

    recent_workouts = await _get_recent_workouts(user["id"])
    recent_meals = await _get_recent_meals(user["id"])
    user_context = _build_user_context(user, recent_workouts, recent_meals, original_text)

    system_prompt = f"{TRAINER_CHAT_WORKOUT_SYSTEM}\n\n{user_context}\n\nmuscle_groups: [{target_muscle_group}]"

    chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            chat_messages.append({"role": role, "content": content})

    chat_messages.append({
        "role": "user",
        "content": "Сформируй итоговую тренировку, учитывая все пожелания из диалога.",
    })

    logger.info("trainer_chat_finish", extra={"session_id": session["id"], "user_id": user["id"]})

    parsed = await ai_service.generate_trainer_workout(chat_messages)
    normalized = ai_service._normalize_structured_workout(parsed, fallback_muscle_group=target_muscle_group)

    calories_burned: int | None = normalized.get("estimated_calories")
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


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

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
    return "\n".join([
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
    ])


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


def _build_chat_messages(session: dict, user: dict, messages: list[dict]) -> list[dict[str, str]]:
    """Build the full message list for OpenAI chat."""
    original_workout_text = session.get("original_workout_text")
    if not isinstance(original_workout_text, str) or not original_workout_text.strip():
        original_details = session.get("original_workout_details")
        original_workout_text = _details_to_response_fields(original_details)[0]

    recent_workouts_sync = []
    recent_meals_sync = []

    user_context = _build_user_context(user, recent_workouts_sync, recent_meals_sync, original_workout_text)
    system_prompt = _build_system_prompt(user_context)

    chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role in ("user", "assistant"):
            chat_messages.append({"role": role, "content": content})

    return chat_messages


def _resolve_target_muscle_group(workout: dict) -> str:
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
            pass
    return target_muscle_group or "Тренировка"
