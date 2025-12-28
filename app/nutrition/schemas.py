from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class MealBase(BaseModel):
    description: str
    calories: Optional[int] = None
    proteins: Optional[int] = None
    fats: Optional[int] = None
    carbs: Optional[int] = None


class MealCreate(MealBase):
    date: Optional[date] = None
    photo_url: Optional[str] = None


class MealResponse(MealBase):
    id: str
    user_id: str
    date: date
    photo_url: Optional[str] = None
    created_at: Optional[datetime] = None


class MealListResponse(BaseModel):
    items: list[MealResponse]
    total: int


class FoodAnalyzeRequest(BaseModel):
    image_url: str
    clarification: Optional[str] = None
    clarifications: Optional[list[str]] = None
    initial_description: Optional[str] = None


class FoodAnalyzeResponse(BaseModel):
    description: str
    calories: Optional[int] = None
    proteins: Optional[int] = None
    fats: Optional[int] = None
    carbs: Optional[int] = None


class DailyNutritionStatsResponse(BaseModel):
    date: date
    total_calories: int
    total_proteins: int
    total_fats: int
    total_carbs: int
    meals_count: int
    target_calories: Optional[int] = None
    target_proteins: Optional[int] = None
    target_fats: Optional[int] = None
    target_carbs: Optional[int] = None


class NutritionPlanBase(BaseModel):
    nutrition_goal: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    meal_preferences: Optional[str] = None
    cooking_time: Optional[str] = None
    budget: Optional[str] = None


class NutritionPlanCreate(NutritionPlanBase):
    pass


class NutritionPlanResponse(NutritionPlanBase):
    id: str
    user_id: str
    is_active: bool
    target_calories: Optional[int] = None
    target_proteins: Optional[int] = None
    target_fats: Optional[int] = None
    target_carbs: Optional[int] = None
    created_at: Optional[datetime] = None


class KBJURecommendations(BaseModel):
    target_calories: int
    target_proteins: int
    target_fats: int
    target_carbs: int
    remaining_calories: int
    remaining_proteins: int
    remaining_fats: int
    remaining_carbs: int
    recommendations: list[str]


class NutritionPlanMenuResponse(BaseModel):
    id: str
    plan_id: str
    date: date
    menu_text: str
    created_at: Optional[datetime] = None


class ShoppingListRequest(BaseModel):
    menu_id: Optional[str] = None
    menu_text: Optional[str] = None


class ShoppingListResponse(BaseModel):
    shopping_list: str

