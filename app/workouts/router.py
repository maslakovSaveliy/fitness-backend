import json
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from app.dependencies import get_current_user, get_current_paid_user
from .schemas import (
    WorkoutCreate,
    WorkoutResponse,
    WorkoutGenerateRequest,
    WorkoutGenerateResponse,
    WorkoutRateRequest,
    WorkoutStatsResponse,
	WorkoutListResponse,
	MuscleGroupsResponse,
	NextMuscleGroupResponse,
	ManualWorkoutAnalyzeRequest,
	ManualWorkoutAnalyzeResponse,
    WorkoutDraftCreateRequest,
    WorkoutDraftCompleteRequest,
    WorkoutDraftCloneRequest,
)
from .service import (
    get_user_workouts,
    create_workout,
    create_workout_draft,
    delete_workout_draft,
    replace_workout_draft,
    replace_workout_exercise,
    complete_workout_draft,
    clone_completed_workout_to_draft,
    generate_workout,
    rate_workout,
    get_workout_stats,
	get_workout_by_id,
	get_available_muscle_groups,
	get_next_muscle_group_for_user,
	analyze_manual_workout,
	get_workout_dates,
)

router = APIRouter(prefix="/workouts", tags=["workouts"])

def _details_to_response_fields(details_value: object) -> tuple[str, object | None]:
    # details в проде jsonb: либо строка (legacy), либо объект (структура 1-в-1).
    if isinstance(details_value, str):
        return details_value, None
    if isinstance(details_value, dict):
        # Пытаемся трактовать как WorkoutStructured (dict). Текст для legacy UI формируем на бэке.
        try:
            from .schemas import WorkoutStructured
            structured = WorkoutStructured.model_validate(details_value)
            from .service import _format_workout_text
            return _format_workout_text(structured), details_value
        except Exception:
            # Непонятный json — отдадим строкой, чтобы не падать.
            return json.dumps(details_value, ensure_ascii=False), None
    return "", None


@router.get("", response_model=WorkoutListResponse)
async def list_workouts(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user)
):
    """Получить список тренировок пользователя."""
    workouts, total = await get_user_workouts(user["id"], limit, offset)
    
    items = [
        WorkoutResponse(
            id=w["id"],
            user_id=w["user_id"],
            date=w["date"],
            workout_type=w["workout_type"],
            details=_details_to_response_fields(w.get("details"))[0],
            details_structured=_details_to_response_fields(w.get("details"))[1],
            calories_burned=w.get("calories_burned"),
            status=w.get("status"),
            rating=w.get("rating"),
            comment=w.get("comment"),
            created_at=w.get("created_at")
        )
        for w in workouts
    ]
    
    return WorkoutListResponse(items=items, total=total)


@router.post("", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def add_workout(
    data: WorkoutCreate,
    user: dict = Depends(get_current_paid_user)
):
    """Сохранить выполненную тренировку."""
    try:
        workout = await create_workout(user["id"], data)
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workout"
        )
    
    return WorkoutResponse(
        id=workout["id"],
        user_id=workout["user_id"],
        date=workout["date"],
        workout_type=workout["workout_type"],
        details=_details_to_response_fields(workout.get("details"))[0],
        details_structured=_details_to_response_fields(workout.get("details"))[1],
        calories_burned=workout.get("calories_burned"),
        status=workout.get("status"),
        rating=workout.get("rating"),
        comment=workout.get("comment"),
        created_at=workout.get("created_at")
    )


@router.post("/drafts", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(
    data: WorkoutDraftCreateRequest,
    user: dict = Depends(get_current_paid_user),
):
    """Создать draft-тренировку (генерация через AI), не попадает в историю пока не completed."""
    try:
        draft = await create_workout_draft(user, data)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if not draft:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create draft")

    details_text, details_structured = _details_to_response_fields(draft.get("details"))
    return WorkoutResponse(
        id=draft["id"],
        user_id=draft["user_id"],
        date=draft["date"],
        workout_type=draft["workout_type"],
        details=details_text,
        details_structured=details_structured,
        calories_burned=draft.get("calories_burned"),
        status=draft.get("status"),
        rating=draft.get("rating"),
        comment=draft.get("comment"),
        created_at=draft.get("created_at"),
    )


@router.delete("/{workout_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_draft(
    workout_id: str,
    user: dict = Depends(get_current_paid_user),
):
    """Удалить draft (best-effort)."""
    try:
        await delete_workout_draft(user["id"], workout_id)
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return None


@router.post("/{workout_id}/replace", response_model=WorkoutResponse)
async def replace_draft(
    workout_id: str,
    user: dict = Depends(get_current_paid_user),
):
    """Перегенерировать всю draft-тренировку."""
    try:
        updated = await replace_workout_draft(user, workout_id)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")

    details_text, details_structured = _details_to_response_fields(updated.get("details"))
    return WorkoutResponse(
        id=updated["id"],
        user_id=updated["user_id"],
        date=updated["date"],
        workout_type=updated["workout_type"],
        details=details_text,
        details_structured=details_structured,
        calories_burned=updated.get("calories_burned"),
        status=updated.get("status"),
        rating=updated.get("rating"),
        comment=updated.get("comment"),
        created_at=updated.get("created_at"),
    )


@router.post("/{workout_id}/exercises/{index}/replace", response_model=WorkoutResponse)
async def replace_exercise(
    workout_id: str,
    index: int,
    user: dict = Depends(get_current_paid_user),
):
    """Перегенерировать одно упражнение (по индексу) внутри draft-тренировки."""
    try:
        updated = await replace_workout_exercise(user, workout_id, index)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")

    details_text, details_structured = _details_to_response_fields(updated.get("details"))
    return WorkoutResponse(
        id=updated["id"],
        user_id=updated["user_id"],
        date=updated["date"],
        workout_type=updated["workout_type"],
        details=details_text,
        details_structured=details_structured,
        calories_burned=updated.get("calories_burned"),
        status=updated.get("status"),
        rating=updated.get("rating"),
        comment=updated.get("comment"),
        created_at=updated.get("created_at"),
    )


@router.post("/{workout_id}/complete", response_model=WorkoutResponse)
async def complete_draft(
    workout_id: str,
    data: WorkoutDraftCompleteRequest,
    user: dict = Depends(get_current_paid_user),
):
    """Сохранить итоговую тренировку: перевод draft → completed с финальными значениями из селектов."""
    try:
        updated = await complete_workout_draft(user["id"], workout_id, data)
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")

    details_text, details_structured = _details_to_response_fields(updated.get("details"))
    return WorkoutResponse(
        id=updated["id"],
        user_id=updated["user_id"],
        date=updated["date"],
        workout_type=updated["workout_type"],
        details=details_text,
        details_structured=details_structured,
        calories_burned=updated.get("calories_burned"),
        status=updated.get("status"),
        rating=updated.get("rating"),
        comment=updated.get("comment"),
        created_at=updated.get("created_at"),
    )


@router.post("/{workout_id}/clone-draft", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def clone_completed_to_draft(
    workout_id: str,
    data: WorkoutDraftCloneRequest | None = Body(default=None),
    user: dict = Depends(get_current_paid_user),
):
    """Клонировать completed-тренировку в draft, чтобы пользователь мог заменить/обсудить/выполнить как новую."""
    draft_date = (data.date if data and data.date else datetime.utcnow().date())
    try:
        draft = await clone_completed_workout_to_draft(user, workout_id, draft_date)
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")

    details_text, details_structured = _details_to_response_fields(draft.get("details"))
    return WorkoutResponse(
        id=draft["id"],
        user_id=draft["user_id"],
        date=draft["date"],
        workout_type=draft["workout_type"],
        details=details_text,
        details_structured=details_structured,
        calories_burned=draft.get("calories_burned"),
        status=draft.get("status"),
        rating=draft.get("rating"),
        comment=draft.get("comment"),
        created_at=draft.get("created_at"),
    )


@router.post("/generate", response_model=WorkoutGenerateResponse)
async def generate_new_workout(
    data: WorkoutGenerateRequest,
    user: dict = Depends(get_current_paid_user)
):
    """Сгенерировать новую тренировку через AI."""
    selected_muscle_groups = data.muscle_groups
    if not selected_muscle_groups and data.muscle_group:
        selected_muscle_groups = [data.muscle_group]

    target = ", ".join(selected_muscle_groups) if selected_muscle_groups else None

    try:
        workout_text, muscle_group, workout_structured = await generate_workout(
            user,
            target_muscle_group=target,
            wellbeing_reason=data.wellbeing_reason,
            selected_muscle_groups=selected_muscle_groups,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )
    
    return WorkoutGenerateResponse(
        workout_text=workout_text,
        muscle_group=muscle_group,
        workout_structured=workout_structured,
    )


@router.get("/muscle-groups", response_model=MuscleGroupsResponse)
async def list_muscle_groups(user: dict = Depends(get_current_paid_user)):
    """Получить список доступных групп мышц (обычный/PRO)."""
    items = get_available_muscle_groups(user)
    return MuscleGroupsResponse(items=items, is_pro=bool(user.get("is_pro", False)))


@router.post("/muscle-groups/next", response_model=NextMuscleGroupResponse)
async def next_muscle_group(user: dict = Depends(get_current_paid_user)):
    """Получить следующую группу мышц по ротации (как в боте)."""
    muscle_group = await get_next_muscle_group_for_user(user)
    return NextMuscleGroupResponse(muscle_group=muscle_group)


@router.post("/manual/analyze", response_model=ManualWorkoutAnalyzeResponse)
async def analyze_manual_workout_endpoint(
    data: ManualWorkoutAnalyzeRequest,
    user: dict = Depends(get_current_paid_user),
):
    """Проанализировать описание ручной тренировки (улучшить текст, оценить калории, дать совет)."""
    result = await analyze_manual_workout(user, data.description)
    return ManualWorkoutAnalyzeResponse(**result)


@router.post("/{workout_id}/rate", response_model=WorkoutResponse)
async def rate_workout_endpoint(
    workout_id: str,
    data: WorkoutRateRequest,
    user: dict = Depends(get_current_user)
):
    """Оценить тренировку."""
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating must be between 1 and 5"
        )
    
    existing = await get_workout_by_id(workout_id, user["id"])
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found"
        )
    
    workout = await rate_workout(workout_id, data)
    
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rate workout"
        )
    
    return WorkoutResponse(
        id=workout["id"],
        user_id=workout["user_id"],
        date=workout["date"],
        workout_type=workout["workout_type"],
        details=_details_to_response_fields(workout.get("details"))[0],
        details_structured=_details_to_response_fields(workout.get("details"))[1],
        calories_burned=workout.get("calories_burned"),
        status=workout.get("status"),
        rating=workout.get("rating"),
        comment=workout.get("comment"),
        created_at=workout.get("created_at")
    )


@router.get("/stats", response_model=WorkoutStatsResponse)
async def get_stats(user: dict = Depends(get_current_user)):
    """Получить статистику тренировок."""
    stats = await get_workout_stats(user["id"])
    return WorkoutStatsResponse(**stats)


@router.get("/dates", response_model=list[str])
async def list_workout_dates(
    year: int | None = Query(None, ge=1970, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    user: dict = Depends(get_current_user),
):
    """Получить уникальные даты тренировок (YYYY-MM-DD) для календаря."""
    if (year is None) ^ (month is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="year and month must be provided together",
        )
    return await get_workout_dates(user["id"], year=year, month=month)


@router.get("/{workout_id}", response_model=WorkoutResponse)
async def get_workout(
    workout_id: str,
    user: dict = Depends(get_current_user)
):
    """Получить тренировку по ID."""
    workout = await get_workout_by_id(workout_id, user["id"])
    
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found"
        )
    
    return WorkoutResponse(
        id=workout["id"],
        user_id=workout["user_id"],
        date=workout["date"],
        workout_type=workout["workout_type"],
        details=_details_to_response_fields(workout.get("details"))[0],
        details_structured=_details_to_response_fields(workout.get("details"))[1],
        calories_burned=workout.get("calories_burned"),
        status=workout.get("status"),
        rating=workout.get("rating"),
        comment=workout.get("comment"),
        created_at=workout.get("created_at")
    )

