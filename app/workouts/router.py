from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.dependencies import get_current_user, get_current_paid_user
from .schemas import (
    WorkoutCreate,
    WorkoutResponse,
    WorkoutGenerateRequest,
    WorkoutGenerateResponse,
    WorkoutRateRequest,
    WorkoutStatsResponse,
    WorkoutListResponse
)
from .service import (
    get_user_workouts,
    create_workout,
    generate_workout,
    rate_workout,
    get_workout_stats,
    get_workout_by_id
)

router = APIRouter(prefix="/workouts", tags=["workouts"])


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
            details=w["details"],
            calories_burned=w.get("calories_burned"),
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
    workout = await create_workout(user["id"], data)
    
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
        details=workout["details"],
        calories_burned=workout.get("calories_burned"),
        rating=workout.get("rating"),
        comment=workout.get("comment"),
        created_at=workout.get("created_at")
    )


@router.post("/generate", response_model=WorkoutGenerateResponse)
async def generate_new_workout(
    data: WorkoutGenerateRequest,
    user: dict = Depends(get_current_paid_user)
):
    """Сгенерировать новую тренировку через AI."""
    workout_text, muscle_group = await generate_workout(user, data.muscle_group)
    
    return WorkoutGenerateResponse(
        workout_text=workout_text,
        muscle_group=muscle_group
    )


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
        details=workout["details"],
        calories_burned=workout.get("calories_burned"),
        rating=workout.get("rating"),
        comment=workout.get("comment"),
        created_at=workout.get("created_at")
    )


@router.get("/stats", response_model=WorkoutStatsResponse)
async def get_stats(user: dict = Depends(get_current_user)):
    """Получить статистику тренировок."""
    stats = await get_workout_stats(user["id"])
    return WorkoutStatsResponse(**stats)


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
        details=workout["details"],
        calories_burned=workout.get("calories_burned"),
        rating=workout.get("rating"),
        comment=workout.get("comment"),
        created_at=workout.get("created_at")
    )

