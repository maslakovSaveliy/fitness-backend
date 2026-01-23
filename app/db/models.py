from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional


class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserProfile(BaseModel):
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


class UserSettings(BaseModel):
    is_pro: bool = False
    supersets_enabled: bool = False
    custom_split_frequency: Optional[int] = None
    last_muscle_group: Optional[str] = None


class UserSubscription(BaseModel):
    is_paid: bool = False
    paid_until: Optional[datetime] = None
    trial_expired: bool = False
    payment_method_id: Optional[str] = None


class User(UserBase, UserProfile, UserSettings, UserSubscription):
    id: str
    role: Optional[str] = None
    has_profile: bool = False
    last_active_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class WorkoutBase(BaseModel):
    workout_type: str
    details: str
    calories_burned: Optional[int] = None


class Workout(WorkoutBase):
    id: str
    user_id: str
    date: date
    rating: Optional[int] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class MealBase(BaseModel):
    description: str
    calories: Optional[int] = None
    proteins: Optional[int] = None
    fats: Optional[int] = None
    carbs: Optional[int] = None
    photo_url: Optional[str] = None


class Meal(MealBase):
    id: str
    user_id: str
    date: date
    created_at: Optional[datetime] = None


class DailyNutritionStats(BaseModel):
    id: str
    user_id: str
    date: date
    total_calories: int = 0
    total_proteins: int = 0
    total_fats: int = 0
    total_carbs: int = 0
    meals_count: int = 0


class NutritionPlanBase(BaseModel):
    nutrition_goal: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    meal_preferences: Optional[str] = None
    cooking_time: Optional[str] = None
    budget: Optional[str] = None
    target_calories: Optional[int] = None
    target_proteins: Optional[int] = None
    target_fats: Optional[int] = None
    target_carbs: Optional[int] = None


class NutritionPlan(NutritionPlanBase):
    id: str
    user_id: str
    is_active: bool = True
    created_at: Optional[datetime] = None

