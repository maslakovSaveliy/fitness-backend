from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserResponse(BaseModel):
    id: str
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    goal: Optional[str] = None
    level: Optional[str] = None
    health_issues: Optional[str] = None
    location: Optional[str] = None
    workouts_per_week: Optional[int] = None
    workout_duration: Optional[str] = None
    equipment: Optional[str] = None
    workout_formats: Optional[str] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    
    is_paid: bool = False
    paid_until: Optional[datetime] = None
    is_pro: bool = False
    supersets_enabled: bool = False
    custom_split_frequency: Optional[int] = None
    last_muscle_group: Optional[str] = None
    trial_expired: bool = False
    
    has_profile: bool = False
    onboarding_completed: bool = False


class ProfileUpdateRequest(BaseModel):
    goal: Optional[str] = None
    level: Optional[str] = None
    health_issues: Optional[str] = None
    location: Optional[str] = None
    workouts_per_week: Optional[int] = None
    workout_duration: Optional[str] = None
    equipment: Optional[str] = None
    workout_formats: Optional[str] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    age: Optional[int] = None
    gender: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    is_pro: Optional[bool] = None
    supersets_enabled: Optional[bool] = None
    custom_split_frequency: Optional[int] = None


class UserStatsResponse(BaseModel):
    total_workouts: int
    month_workouts: int
    total_meals: int
    current_streak: int

