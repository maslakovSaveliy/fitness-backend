from pydantic import BaseModel, field_validator, field_serializer
from typing import Optional, Literal, Union
from datetime import date, datetime


MealType = Literal["breakfast", "lunch", "dinner", "snack", "user"]


class MealBase(BaseModel):
    description: str
    calories: Optional[int] = None
    proteins: Optional[int] = None
    fats: Optional[int] = None
    carbs: Optional[int] = None
    
    @field_validator('calories', 'proteins', 'fats', 'carbs', mode='before')
    @classmethod
    def convert_to_int(cls, v: Union[int, float, None]) -> Optional[int]:
        if v is None:
            return None
        return int(v)


class MealCreate(MealBase):
    date: Optional[str] = None  # Accept as string, parse in service
    photo_url: Optional[str] = None
    meal_type: Optional[MealType] = "user"  # Default "user" for manual entries, plan sets specific type


class MealResponse(MealBase):
    model_config = {"from_attributes": True}
    
    id: str
    user_id: str
    date: date
    photo_url: Optional[str] = None
    meal_type: Optional[str] = None
    created_at: Optional[datetime] = None
    
    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v: Union[date, str]) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v
    
    @field_serializer('date')
    def serialize_date(self, v: date) -> str:
        return v.isoformat() if isinstance(v, date) else str(v)


class MealListResponse(BaseModel):
    items: list[MealResponse]
    total: int


class FoodAnalyzeRequest(BaseModel):
    image_url: str
    clarification: Optional[str] = None
    clarifications: Optional[list[str]] = None
    initial_description: Optional[str] = None


class FoodDescriptionRequest(BaseModel):
    description: str


class FoodAnalyzeResponse(BaseModel):
    description: str
    calories: Optional[int] = None
    proteins: Optional[int] = None
    fats: Optional[int] = None
    carbs: Optional[int] = None
    
    @field_validator('calories', 'proteins', 'fats', 'carbs', mode='before')
    @classmethod
    def convert_to_int(cls, v: int | float | None) -> int | None:
        if v is None:
            return None
        return int(v)


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


class DailyMenuMeal(BaseModel):
    name: str
    calories: int
    proteins: int
    fats: int
    carbs: int


class DailyMenuSection(BaseModel):
    type: Literal["breakfast", "lunch", "dinner", "snacks"]
    title: str
    time_range: str
    items: list[DailyMenuMeal]


class DailyMenuStructured(BaseModel):
    model_config = {"extra": "ignore"}  # Ignore extra fields like day_of_week, day_name
    
    target_calories: int = 2000
    target_proteins: int = 100
    target_fats: int = 70
    target_carbs: int = 250
    sections: list[DailyMenuSection] = []
    tip_of_day: str = ""


class DailyMenuStructuredResponse(BaseModel):
    id: str
    plan_id: str
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    menu_structured: DailyMenuStructured
    created_at: Optional[datetime] = None


class WeekMenuResponse(BaseModel):
    plan_id: str
    days: list[Optional[DailyMenuStructuredResponse]]  # 7 elements, index = day_of_week
    has_menu: bool


class ShoppingListRequest(BaseModel):
    menu_id: Optional[str] = None
    menu_text: Optional[str] = None


class ShoppingListResponse(BaseModel):
    shopping_list: str

