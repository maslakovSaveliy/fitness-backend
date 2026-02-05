import json
from uuid import uuid4
from datetime import date as dt_date, datetime, timedelta
from app.ai.prompts import (
    MUSCLE_GROUPS_COMBINED,
    MUSCLE_GROUPS_SINGLE,
    PRO_MUSCLE_GROUPS_MEN,
    PRO_MUSCLE_GROUPS_WOMEN,
    PRO_MUSCLE_SETS_MEN,
    PRO_MUSCLE_SETS_WOMEN,
)
from app.db import supabase_client
from app.ai import ai_service
from app.ai.prompts import WORKOUT_SPLITS, SPLIT_DESCRIPTIONS
from .schemas import (
    WorkoutCreate,
    WorkoutRateRequest,
    WorkoutStructured,
    WorkoutStructuredExercise,
    WorkoutDraftCreateRequest,
    WorkoutDraftCompleteRequest,
    ManualWorkoutLogRequest,
)
from app.users.service import calculate_workout_streak


async def get_user_workouts(
    user_id: str,
    limit: int = 10,
    offset: int = 0
) -> tuple[list[dict], int]:
    params = {
        "user_id": f"eq.{user_id}",
        "status": "eq.completed",
        # Для "последней тренировки" важно сортировать по времени создания/обновления,
        # а не только по date (она может совпадать у нескольких тренировок).
        # PostgREST поддерживает multi-order через запятую.
        "order": "updated_at.desc,created_at.desc,date.desc",
        "limit": str(limit),
        "offset": str(offset)
    }
    workouts = await supabase_client.get("workouts", params)
    
    count_result = await supabase_client.get(
        "workouts",
        {"user_id": f"eq.{user_id}", "status": "eq.completed", "select": "id"}
    )
    total = len(count_result) if count_result else 0
    
    return workouts, total


def _infer_target_muscle_group_from_details(details_value: object) -> str | None:
    if not isinstance(details_value, dict):
        return None
    try:
        structured = WorkoutStructured.model_validate(details_value)
        if structured.muscle_groups:
            return ", ".join(structured.muscle_groups[:2])
    except Exception:
        return None
    return None


async def clone_completed_workout_to_draft(
    user: dict,
    workout_id: str,
    draft_date: dt_date,
) -> dict | None:
    source = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.completed"},
    )
    if not source:
        return None

    details_value = source.get("details")
    source_ctx = source.get("generation_context") if isinstance(source.get("generation_context"), dict) else None
    target_muscle_group = None
    if source_ctx and isinstance(source_ctx.get("target_muscle_group"), str):
        tmg = source_ctx.get("target_muscle_group")
        if tmg and tmg.strip():
            target_muscle_group = tmg.strip()
    if not target_muscle_group:
        target_muscle_group = _infer_target_muscle_group_from_details(details_value)

    generation_context: dict[str, object] = {
        "mode": "clone_last",
        "cloned_from_workout_id": source.get("id"),
    }
    if source_ctx:
        generation_context.update(source_ctx)
    if target_muscle_group:
        generation_context["target_muscle_group"] = target_muscle_group

    draft_data: dict[str, object] = {
        "id": str(uuid4()),
        "user_id": user["id"],
        "date": draft_date.isoformat(),
        "workout_type": source.get("workout_type") or "ai",
        "details": details_value,
        "status": "draft",
        "generation_context": generation_context,
        "calories_burned": source.get("calories_burned"),
    }

    created = await supabase_client.insert("workouts", draft_data)
    return created[0] if created else None


async def create_workout(user_id: str, data: WorkoutCreate) -> dict:
    workout_date = data.date or dt_date.today()
    
    # В продовой схеме workouts.details = jsonb.
    # - если есть details_structured -> пишем объект
    # - иначе пишем строку (jsonb-строка), чтобы поддержать legacy
    details_json: object
    if data.details_structured is not None:
        details_json = data.details_structured.model_dump()
    else:
        details_json = data.details

    workout_data = {
        "id": str(uuid4()),
        "user_id": user_id,
        "date": workout_date.isoformat(),
        "workout_type": data.workout_type,
        "details": details_json,
        "status": "completed",
    }
    
    if data.calories_burned is not None:
        workout_data["calories_burned"] = data.calories_burned
    
    result = await supabase_client.insert("workouts", workout_data)
    return result[0] if result else None


def _draft_workout_type(
    wellbeing_reason: str | None, selected_muscle_groups: list[str] | None
) -> str:
    if wellbeing_reason:
        return "wellbeing"
    if selected_muscle_groups:
        return "personal"
    return "ai"


async def create_workout_draft(user: dict, data: WorkoutDraftCreateRequest) -> dict:
    selected_muscle_groups = data.muscle_groups
    if not selected_muscle_groups and data.muscle_group:
        selected_muscle_groups = [data.muscle_group]

    is_wellbeing_mode = data.mode == "wellbeing" and isinstance(data.wellbeing_reason, str) and data.wellbeing_reason.strip()

    target = ", ".join(selected_muscle_groups) if selected_muscle_groups else None
    used_muscle_group = target or await get_next_muscle_group_for_user(user)

    # В wellbeing-режиме AI сам выбирает группы мышц — last_muscle_group обновляем ПОСЛЕ генерации.
    if not is_wellbeing_mode:
        # 1-в-1 с ботом: last_muscle_group обновляется ДО генерации.
        if selected_muscle_groups and isinstance(selected_muscle_groups[0], str):
            await _update_last_muscle_group(user["id"], selected_muscle_groups[0])
        else:
            await _update_last_muscle_group(user["id"], used_muscle_group)

    if is_wellbeing_mode:
        workout_structured_raw = await ai_service.generate_wellbeing_workout_structured(
            user=user,
            wellbeing_reason=data.wellbeing_reason.strip(),
        )
    else:
        workout_structured_raw = await ai_service.generate_workout_structured(
            user,
            target_muscle_group=used_muscle_group,
            wellbeing_reason=data.wellbeing_reason,
        )
    # estimated_calories приходит из AI-сервиса, сохраняем в calories_burned в БД
    calories_raw = workout_structured_raw.get("estimated_calories")
    calories_burned: int | None = None
    if isinstance(calories_raw, int) and calories_raw > 0:
        calories_burned = calories_raw
    if isinstance(calories_raw, float):
        calories_burned = int(calories_raw)
    if isinstance(calories_raw, str):
        try:
            calories_burned = int(float(calories_raw))
        except Exception:
            calories_burned = None

    workout_structured = WorkoutStructured.model_validate(workout_structured_raw)

    if is_wellbeing_mode and workout_structured.muscle_groups:
        await _update_last_muscle_group(user["id"], workout_structured.muscle_groups[0])

    workout_data = {
        "id": str(uuid4()),
        "user_id": user["id"],
        "date": data.date.isoformat(),
        "workout_type": _draft_workout_type(data.wellbeing_reason, selected_muscle_groups),
        "details": workout_structured.model_dump(),
        "status": "draft",
        "generation_context": {
            "muscle_groups": selected_muscle_groups,
            "target_muscle_group": ", ".join(workout_structured.muscle_groups) if is_wellbeing_mode else used_muscle_group,
            "wellbeing_reason": data.wellbeing_reason,
            "mode": data.mode,
        },
        "calories_burned": calories_burned,
    }

    created = await supabase_client.insert("workouts", workout_data)
    row = created[0] if created else None
    if not row:
        return None

    return row


async def get_active_draft(user_id: str) -> dict | None:
    """Получить активный draft пользователя (последний по дате создания)."""
    drafts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "status": "eq.draft",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    return drafts[0] if drafts else None


async def delete_workout_draft(user_id: str, workout_id: str) -> bool:
    existing = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "status": "eq.draft"},
    )
    if not existing:
        return False
    await supabase_client.delete(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "status": "eq.draft"},
    )
    return True


async def replace_workout_draft(user: dict, workout_id: str) -> dict | None:
    workout = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.draft"},
    )
    if not workout:
        return None

    ctx = workout.get("generation_context") or {}
    selected_muscle_groups = ctx.get("muscle_groups")
    if not isinstance(selected_muscle_groups, list):
        selected_muscle_groups = None
    target_muscle_group = ctx.get("target_muscle_group")
    if not isinstance(target_muscle_group, str) or not target_muscle_group.strip():
        target_muscle_group = None
    wellbeing_reason = ctx.get("wellbeing_reason")
    if not isinstance(wellbeing_reason, str):
        wellbeing_reason = None
    if isinstance(wellbeing_reason, str):
        wellbeing_reason = wellbeing_reason.strip() or None

    mode = ctx.get("mode")
    if not isinstance(mode, str):
        mode = None
    is_wellbeing_mode = mode == "wellbeing" and wellbeing_reason is not None

    # Для случайной AI-тренировки (без выбранных мышц и без wellbeing) при "Заменить"
    # должны меняться группы мышц по ротации (как в боте).
    is_random_ai = (
        workout.get("workout_type") == "ai"
        and not selected_muscle_groups
        and wellbeing_reason is None
    )

    if is_wellbeing_mode:
        avoid_exercise_names: list[str] | None = None
        try:
            current_details = workout.get("details")
            if isinstance(current_details, dict):
                current_structured = WorkoutStructured.model_validate(current_details)
                avoid_exercise_names = [ex.name for ex in current_structured.exercises if ex.name]
        except Exception:
            avoid_exercise_names = None

        workout_structured_raw = await ai_service.generate_wellbeing_workout_structured(
            user=user,
            wellbeing_reason=wellbeing_reason,
            avoid_exercise_names=avoid_exercise_names,
        )
        workout_structured = WorkoutStructured.model_validate(workout_structured_raw)
        if workout_structured.muscle_groups:
            await _update_last_muscle_group(user["id"], workout_structured.muscle_groups[0])
        target = ", ".join(workout_structured.muscle_groups) if workout_structured.muscle_groups else None
    elif is_random_ai:
        used_muscle_group = await get_next_muscle_group_for_user(user)
        await _update_last_muscle_group(user["id"], used_muscle_group)
        target = used_muscle_group
        workout_structured_raw = await ai_service.generate_workout_structured(
            user,
            target_muscle_group=target,
            wellbeing_reason=wellbeing_reason,
        )
        workout_structured = WorkoutStructured.model_validate(workout_structured_raw)
    else:
        target = target_muscle_group or (
            ", ".join(selected_muscle_groups) if selected_muscle_groups else None
        )
        workout_structured_raw = await ai_service.generate_workout_structured(
            user,
            target_muscle_group=target or WorkoutStructured.model_validate(workout.get("details")).muscle_groups[0],
            wellbeing_reason=wellbeing_reason,
        )
        workout_structured = WorkoutStructured.model_validate(workout_structured_raw)

    calories_raw = workout_structured_raw.get("calories_burned")
    calories_burned: int | None = None
    if isinstance(calories_raw, int) and calories_raw > 0:
        calories_burned = calories_raw
    if isinstance(calories_raw, float):
        calories_burned = int(calories_raw)

    update_data: dict[str, object] = {
        "details": workout_structured.model_dump(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    if calories_burned is not None:
        update_data["calories_burned"] = calories_burned

    if is_random_ai or is_wellbeing_mode:
        existing_ctx = ctx if isinstance(ctx, dict) else {}
        update_data["generation_context"] = {
            **existing_ctx,
            "target_muscle_group": target,
        }

    updated = await supabase_client.update(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.draft"},
        update_data,
    )
    return updated[0] if updated else None


async def replace_workout_exercise(user: dict, workout_id: str, index: int) -> dict | None:
    workout = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.draft"},
    )
    if not workout:
        return None

    details_value = workout.get("details")
    if not isinstance(details_value, dict):
        return None

    structured = WorkoutStructured.model_validate(details_value)
    if index < 0 or index >= len(structured.exercises):
        return None

    ctx = workout.get("generation_context") or {}
    target_muscle_group = ctx.get("target_muscle_group")
    if not isinstance(target_muscle_group, str) or not target_muscle_group.strip():
        muscle_groups = ctx.get("muscle_groups")
        if not isinstance(muscle_groups, list) or not muscle_groups:
            muscle_groups = structured.muscle_groups
        target_muscle_group = (
            ", ".join([str(x) for x in muscle_groups if isinstance(x, str)]) or structured.muscle_groups[0]
        )

    existing_names = [ex.name for ex in structured.exercises]
    new_ex_raw = await ai_service.generate_workout_exercise(
        user=user,
        muscle_group=target_muscle_group,
        existing_exercise_names=existing_names,
    )
    new_ex = WorkoutStructuredExercise.model_validate(new_ex_raw)

    structured.exercises[index] = new_ex

    updated = await supabase_client.update(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user['id']}", "status": "eq.draft"},
        {"details": structured.model_dump(), "updated_at": datetime.utcnow().isoformat()},
    )
    return updated[0] if updated else None


async def complete_workout_draft(user_id: str, workout_id: str, data: WorkoutDraftCompleteRequest) -> dict | None:
    existing = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "status": "eq.draft"},
    )
    if not existing:
        return None

    update_data: dict[str, object] = {
        "status": "completed",
        "date": data.date.isoformat(),
        "details": data.details_structured.model_dump(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    if data.calories_burned is not None:
        update_data["calories_burned"] = data.calories_burned

    if data.rating is not None:
        update_data["rating"] = int(data.rating)

    updated = await supabase_client.update(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "status": "eq.draft"},
        update_data,
    )
    return updated[0] if updated else None


def _is_female_gender(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return lowered.startswith("ж")


def get_available_muscle_groups(user: dict) -> list[str]:
    if user.get("is_pro"):
        if _is_female_gender(user.get("gender")):
            return PRO_MUSCLE_GROUPS_WOMEN
        return PRO_MUSCLE_GROUPS_MEN
    return MUSCLE_GROUPS_SINGLE


def _get_next_pro_muscle_set(user: dict) -> list[str]:
    sets = PRO_MUSCLE_SETS_WOMEN if _is_female_gender(user.get("gender")) else PRO_MUSCLE_SETS_MEN
    last = user.get("last_muscle_group")
    idx = -1
    if last:
        for i, s in enumerate(sets):
            joined = ", ".join(s)
            if last == joined or last in s:
                idx = i
                break
    next_idx = (idx + 1) % len(sets)
    return sets[next_idx]


async def get_next_muscle_group_for_user(user: dict) -> str:
    if user.get("is_pro"):
        return ", ".join(_get_next_pro_muscle_set(user))

    # 1-в-1 с bot/db.py:get_next_muscle_group — ротация по MUSCLE_GROUPS_COMBINED
    rotation = MUSCLE_GROUPS_COMBINED
    last_muscle_group = user.get("last_muscle_group")
    if not last_muscle_group:
        return rotation[0]
    try:
        current_index = rotation.index(last_muscle_group)
        next_index = (current_index + 1) % len(rotation)
        return rotation[next_index]
    except ValueError:
        return rotation[0]


async def _update_last_muscle_group(user_id: str, muscle_group: str) -> None:
    await supabase_client.update(
        "users",
        {"id": f"eq.{user_id}"},
        {"last_muscle_group": muscle_group},
    )


async def generate_workout(
    user: dict,
    target_muscle_group: str | None = None,
    wellbeing_reason: str | None = None,
    selected_muscle_groups: list[str] | None = None,
) -> tuple[str, str, WorkoutStructured]:
    used_muscle_group = target_muscle_group or await get_next_muscle_group_for_user(user)

    # 1-в-1 с ботом: last_muscle_group обновляется ДО генерации.
    # - AI-генерация: пишем выбранную ротацией группу (или PRO-набор строкой)
    # - manual selection: пишем первую выбранную группу
    if selected_muscle_groups and isinstance(selected_muscle_groups[0], str):
        await _update_last_muscle_group(user["id"], selected_muscle_groups[0])
    else:
        await _update_last_muscle_group(user["id"], used_muscle_group)

    workout_structured_raw = await ai_service.generate_workout_structured(
        user,
        target_muscle_group=used_muscle_group,
        wellbeing_reason=wellbeing_reason,
    )
    workout_structured = WorkoutStructured.model_validate(workout_structured_raw)
    workout_text = _format_workout_text(workout_structured)

    return workout_text, used_muscle_group, workout_structured


def _format_workout_text(workout: WorkoutStructured) -> str:
    lines: list[str] = []
    lines.append(workout.title)
    lines.append("")
    lines.append(f"Мышцы: {', '.join(workout.muscle_groups)}")
    lines.append("")

    for idx, ex in enumerate(workout.exercises, 1):
        lines.append(f"{idx}. {ex.name}")
        weight_label = f"{ex.weight_kg} кг" if ex.weight_kg > 0 else "собственный вес"
        lines.append(f"{ex.sets}×{ex.reps} — {weight_label}")
        lines.append("")

    return "\n".join(lines).strip()


def _extract_json_object(raw: str) -> dict | None:
    json_start = raw.find("{")
    json_end = raw.rfind("}")
    if json_start == -1 or json_end == -1 or json_end <= json_start:
        return None
    try:
        return json.loads(raw[json_start : json_end + 1])
    except Exception:
        return None


async def analyze_manual_workout(user: dict, description: str) -> dict:
    raw = await ai_service.analyze_manual_workout(description, user)
    parsed = _extract_json_object(raw)
    if not parsed:
        return {
            "improved_description": description,
            "calories_burned": None,
            "post_workout_advice": "Отличная работа! Продолжай в том же духе! 💪",
        }

    improved_description = parsed.get("improved_description") or description
    post_workout_advice = parsed.get("post_workout_advice") or "Отличная работа! Продолжай в том же духе! 💪"
    calories_burned = parsed.get("calories_burned")
    if isinstance(calories_burned, bool):
        calories_burned = None
    if isinstance(calories_burned, float):
        calories_burned = int(calories_burned)
    if isinstance(calories_burned, str):
        try:
            calories_burned = int(float(calories_burned))
        except Exception:
            calories_burned = None

    if not isinstance(calories_burned, int):
        calories_burned = None

    return {
        "improved_description": str(improved_description),
        "calories_burned": calories_burned,
        "post_workout_advice": str(post_workout_advice),
    }


def _normalize_manual_log_exercise_name(value: str) -> str:
    return " ".join(value.strip().split())


def _to_int(value: object, default_value: int = 0) -> int:
    if isinstance(value, bool):
        return default_value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except Exception:
            return default_value
    return default_value


async def log_manual_workout(user: dict, data: ManualWorkoutLogRequest) -> dict | None:
    # 1) Фильтруем и нормализуем упражнения (пустые названия выкидываем).
    cleaned: list[WorkoutStructuredExercise] = []
    for ex in data.exercises:
        name = _normalize_manual_log_exercise_name(ex.name)
        if not name:
            continue

        weight_kg = max(0, _to_int(ex.weight_kg, 0))
        sets = max(0, _to_int(ex.sets, 0))
        reps = max(0, _to_int(ex.reps, 0))

        # Для structured схемы мы храним числа, но UI уже умеет не показывать селекты если 0.
        cleaned.append(
            WorkoutStructuredExercise(
                name=name,
                weight_kg=weight_kg,
                sets=sets,
                reps=reps,
            )
        )

    if not cleaned:
        return None

    # 2) AI-метаданные (title, muscle_groups, calories_burned)
    exercises_for_ai: list[dict[str, object]] = [
        {
            "name": ex.name,
            "weight_kg": ex.weight_kg,
            "sets": ex.sets,
            "reps": ex.reps,
        }
        for ex in cleaned
    ]

    meta_raw = await ai_service.infer_manual_workout_metadata(user=user, exercises=exercises_for_ai)
    title_value = meta_raw.get("title")
    muscle_groups_value = meta_raw.get("muscle_groups")
    calories_value = meta_raw.get("calories_burned")

    title = str(title_value).strip() if isinstance(title_value, (str, int, float)) else "Записанная тренировка"
    if not title:
        title = "Записанная тренировка"
    if len(title) > 120:
        title = title[:120]

    muscle_groups: list[str] = []
    if isinstance(muscle_groups_value, list):
        for item in muscle_groups_value[:4]:
            if isinstance(item, str) and item.strip():
                muscle_groups.append(item.strip())
    if not muscle_groups:
        muscle_groups = ["Общий комплекс"]

    calories_burned: int | None = None
    if isinstance(calories_value, (int, float, str)):
        try:
            calories_burned = int(float(calories_value))
        except Exception:
            calories_burned = None
    if calories_burned is not None and calories_burned <= 0:
        calories_burned = None

    # 3) Собираем structured workout и сохраняем как completed manual
    structured = WorkoutStructured(
        version=1,
        title=title,
        muscle_groups=muscle_groups,
        exercises=cleaned,
    )

    workout_create = WorkoutCreate(
        workout_type="manual",
        details=_format_workout_text(structured),
        details_structured=structured,
        calories_burned=calories_burned,
        date=data.date,
    )

    return await create_workout(user["id"], workout_create)


async def rate_workout(workout_id: str, data: WorkoutRateRequest) -> dict:
    update_data = {"rating": data.rating}
    if data.comment:
        update_data["comment"] = data.comment
    
    result = await supabase_client.update(
        "workouts",
        {"id": f"eq.{workout_id}"},
        update_data
    )
    return result[0] if result else None


async def get_workout_stats(user_id: str) -> dict:
    all_workouts = await supabase_client.get(
        "workouts",
        {"user_id": f"eq.{user_id}", "status": "eq.completed", "select": "id,date"}
    )
    total_workouts = len(all_workouts) if all_workouts else 0
    
    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_iso = current_month_start.isoformat()[:10]
    
    month_workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "status": "eq.completed",
            "date": f"gte.{month_start_iso}",
            "select": "id"
        }
    )
    month_count = len(month_workouts) if month_workouts else 0
    
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    cutoff_iso = cutoff_date.isoformat()[:10]
    
    recent_workouts = await supabase_client.get(
        "workouts",
        {
            "user_id": f"eq.{user_id}",
            "status": "eq.completed",
            "date": f"gte.{cutoff_iso}",
            "select": "id,date"
        }
    )
    recent_count = len(recent_workouts) if recent_workouts else 0
    average_weekly = round(recent_count / 4.3, 1)
    
    last_workout_date = None
    if all_workouts:
        sorted_workouts = sorted(all_workouts, key=lambda x: x.get("date", ""), reverse=True)
        if sorted_workouts:
            last_workout_date = sorted_workouts[0].get("date")
    
    real_frequency = min(5, max(1, round(average_weekly)))
    recommended_split = SPLIT_DESCRIPTIONS.get(real_frequency, SPLIT_DESCRIPTIONS[3])

    current_streak = await calculate_workout_streak(user_id)
    
    return {
        "current_streak": current_streak,
        "total_workouts": total_workouts,
        "month_workouts": month_count,
        "average_weekly": average_weekly,
        "last_workout_date": last_workout_date,
        "current_split": recommended_split,
        "recommended_split": recommended_split
    }


def _month_range(year: int, month: int) -> tuple[str, str]:
    # month: 1..12
    start = dt_date(year, month, 1)
    if month == 12:
        end = dt_date(year + 1, 1, 1)
    else:
        end = dt_date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


async def get_workout_dates(
    user_id: str,
    year: int | None = None,
    month: int | None = None,
    limit: int = 2000,
) -> list[str]:
    params: dict[str, str] = {
        "user_id": f"eq.{user_id}",
        "status": "eq.completed",
        "select": "date",
        "order": "date.desc",
        "limit": str(limit),
    }

    if year is not None and month is not None:
        start_iso, end_iso = _month_range(year, month)
        # PostgREST: несколько условий на одно поле делаем через and
        params["and"] = f"(date.gte.{start_iso},date.lt.{end_iso})"

    workouts = await supabase_client.get("workouts", params)

    if not workouts:
        return []

    unique_dates: set[str] = set()
    for w in workouts:
        date_value = w.get("date")
        if not date_value:
            continue
        date_str = str(date_value)[:10]
        # ISO yyyy-mm-dd
        if len(date_str) == 10:
            unique_dates.add(date_str)

    return sorted(unique_dates)


async def get_workout_by_id(workout_id: str, user_id: str) -> dict | None:
    workout = await supabase_client.get_one(
        "workouts",
        {"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"}
    )
    return workout


async def get_workouts_in_range(
    user_id: str,
    start_iso: str,
    end_iso: str,
    limit: int = 500,
) -> list[dict]:
    # end_iso не включительно
    params: dict[str, str] = {
        "user_id": f"eq.{user_id}",
        "status": "eq.completed",
        "order": "updated_at.desc,created_at.desc,date.desc",
        "limit": str(limit),
        # PostgREST: несколько условий на одно поле делаем через and
        "and": f"(date.gte.{start_iso},date.lt.{end_iso})",
    }
    workouts = await supabase_client.get("workouts", params)
    return workouts or []

