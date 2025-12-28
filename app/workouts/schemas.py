from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date, datetime


WorkoutStatus = Literal["draft", "completed"]


class WorkoutStructuredExercise(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    weight_kg: int = Field(ge=0, le=500)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=200)


class WorkoutStructured(BaseModel):
    version: int = Field(default=1, ge=1, le=100)
    title: str = Field(min_length=1, max_length=120)
    muscle_groups: list[str] = Field(min_length=1, max_length=4)
    exercises: list[WorkoutStructuredExercise] = Field(min_length=1, max_length=30)


class WorkoutBase(BaseModel):
    workout_type: str
    details: str
    details_structured: Optional[WorkoutStructured] = None
    calories_burned: Optional[int] = None


class WorkoutCreate(WorkoutBase):
    date: Optional[date] = None


class WorkoutResponse(WorkoutBase):
    id: str
    user_id: str
    date: date
    status: Optional[WorkoutStatus] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class WorkoutDraftCreateRequest(BaseModel):
    muscle_group: Optional[str] = None
    muscle_groups: Optional[list[str]] = None
    wellbeing_reason: Optional[str] = None
    mode: Optional[str] = None
    date: date


class WorkoutDraftCompleteRequest(BaseModel):
    date: date
    details_structured: WorkoutStructured
    calories_burned: Optional[int] = None
    rating: Optional[Literal[1, 2, 3, 4, 5]] = None


class WorkoutDraftCloneRequest(BaseModel):
    date: Optional[date] = None


class WorkoutGenerateRequest(BaseModel):
    muscle_group: Optional[str] = None
    muscle_groups: Optional[list[str]] = None
    wellbeing_reason: Optional[str] = None
    mode: Optional[str] = None


class WorkoutGenerateResponse(BaseModel):
    workout_text: str
    muscle_group: str
    workout_structured: WorkoutStructured


class MuscleGroupsResponse(BaseModel):
    items: list[str]
    is_pro: bool


class NextMuscleGroupResponse(BaseModel):
    muscle_group: str


class WorkoutRateRequest(BaseModel):
    rating: int
    comment: Optional[str] = None


class ManualWorkoutAnalyzeRequest(BaseModel):
    description: str


class ManualWorkoutAnalyzeResponse(BaseModel):
    improved_description: str
    calories_burned: Optional[int] = None
    post_workout_advice: str


class WorkoutStatsResponse(BaseModel):
    current_streak: int
    total_workouts: int
    month_workouts: int
    average_weekly: float
    last_workout_date: Optional[date] = None
    current_split: str
    recommended_split: str


class WorkoutListResponse(BaseModel):
    items: list[WorkoutResponse]
    total: int

