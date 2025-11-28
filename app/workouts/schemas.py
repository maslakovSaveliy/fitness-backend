from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class WorkoutBase(BaseModel):
    workout_type: str
    details: str
    calories_burned: Optional[int] = None


class WorkoutCreate(WorkoutBase):
    date: Optional[date] = None


class WorkoutResponse(WorkoutBase):
    id: str
    user_id: str
    date: date
    rating: Optional[int] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class WorkoutGenerateRequest(BaseModel):
    muscle_group: Optional[str] = None


class WorkoutGenerateResponse(BaseModel):
    workout_text: str
    muscle_group: str


class WorkoutRateRequest(BaseModel):
    rating: int
    comment: Optional[str] = None


class WorkoutStatsResponse(BaseModel):
    total_workouts: int
    month_workouts: int
    average_weekly: float
    last_workout_date: Optional[date] = None
    current_split: str
    recommended_split: str


class WorkoutListResponse(BaseModel):
    items: list[WorkoutResponse]
    total: int

