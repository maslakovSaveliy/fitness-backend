from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request

from app.dependencies import get_current_user, get_current_paid_user
from app.rate_limit import limiter, get_ai_rate_limit
from .schemas import (
    MealCreate,
    MealResponse,
    MealListResponse,
    FoodAnalyzeRequest,
    FoodAnalyzeResponse,
    DailyNutritionStatsResponse,
    NutritionPlanCreate,
    NutritionPlanResponse,
    KBJURecommendations
)
from .service import (
    get_user_meals,
    create_meal,
    analyze_food_photo,
    get_daily_nutrition_stats,
    get_active_nutrition_plan,
    create_nutrition_plan,
    get_kbju_recommendations
)

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


def _build_meal_response(m: dict) -> MealResponse:
    """Построить ответ с данными приёма пищи."""
    return MealResponse(
        id=m["id"],
        user_id=m["user_id"],
        date=m["date"],
        description=m["description"],
        calories=m.get("calories"),
        proteins=m.get("proteins"),
        fats=m.get("fats"),
        carbs=m.get("carbs"),
        photo_url=m.get("photo_url"),
        created_at=m.get("created_at")
    )


@router.get("/meals", response_model=MealListResponse)
@limiter.limit("30/minute")
async def list_meals(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    date_filter: date | None = Query(None, alias="date"),
    user: dict = Depends(get_current_user)
):
    """Получить список приемов пищи."""
    meals, total = await get_user_meals(user["id"], limit, offset, date_filter)
    
    items = [_build_meal_response(m) for m in meals]
    
    return MealListResponse(items=items, total=total)


@router.post("/meals", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def add_meal(
    request: Request,
    data: MealCreate,
    user: dict = Depends(get_current_paid_user)
):
    """Добавить прием пищи."""
    meal = await create_meal(user["id"], data)
    
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create meal"
        )
    
    return _build_meal_response(meal)


@router.post("/meals/analyze", response_model=FoodAnalyzeResponse)
@limiter.limit(get_ai_rate_limit())
async def analyze_food(
    request: Request,
    data: FoodAnalyzeRequest,
    user: dict = Depends(get_current_paid_user)
):
    """Анализировать фото еды через AI."""
    result = await analyze_food_photo(data.image_url, data.clarification)
    return result


@router.get("/stats/today", response_model=DailyNutritionStatsResponse)
@limiter.limit("30/minute")
async def get_today_stats(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Получить статистику питания за сегодня."""
    today = date.today()
    
    stats = await get_daily_nutrition_stats(user["id"], today)
    
    return DailyNutritionStatsResponse(
        date=today,
        total_calories=stats.get("total_calories", 0),
        total_proteins=stats.get("total_proteins", 0),
        total_fats=stats.get("total_fats", 0),
        total_carbs=stats.get("total_carbs", 0),
        meals_count=stats.get("meals_count", 0)
    )


@router.get("/stats/{target_date}", response_model=DailyNutritionStatsResponse)
@limiter.limit("30/minute")
async def get_date_stats(
    request: Request,
    target_date: date,
    user: dict = Depends(get_current_user)
):
    """Получить статистику питания за конкретную дату."""
    stats = await get_daily_nutrition_stats(user["id"], target_date)
    
    return DailyNutritionStatsResponse(
        date=target_date,
        total_calories=stats.get("total_calories", 0),
        total_proteins=stats.get("total_proteins", 0),
        total_fats=stats.get("total_fats", 0),
        total_carbs=stats.get("total_carbs", 0),
        meals_count=stats.get("meals_count", 0)
    )


@router.get("/recommendations", response_model=KBJURecommendations)
@limiter.limit("30/minute")
async def get_recommendations(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Получить рекомендации по КБЖУ на сегодня."""
    today = date.today()
    
    stats = await get_daily_nutrition_stats(user["id"], today)
    recommendations = await get_kbju_recommendations(user, stats)
    
    return KBJURecommendations(**recommendations)


@router.get("/plans/active", response_model=NutritionPlanResponse | None)
@limiter.limit("30/minute")
async def get_active_plan(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Получить активный план питания."""
    plan = await get_active_nutrition_plan(user["id"])
    
    if not plan:
        return None
    
    return NutritionPlanResponse(
        id=plan["id"],
        user_id=plan["user_id"],
        is_active=plan["is_active"],
        nutrition_goal=plan.get("nutrition_goal"),
        dietary_restrictions=plan.get("dietary_restrictions"),
        meal_preferences=plan.get("meal_preferences"),
        cooking_time=plan.get("cooking_time"),
        budget=plan.get("budget"),
        target_calories=plan.get("target_calories"),
        target_proteins=plan.get("target_proteins"),
        target_fats=plan.get("target_fats"),
        target_carbs=plan.get("target_carbs"),
        created_at=plan.get("created_at")
    )


@router.post("/plans", response_model=NutritionPlanResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_plan(
    request: Request,
    data: NutritionPlanCreate,
    user: dict = Depends(get_current_paid_user)
):
    """Создать новый план питания."""
    plan = await create_nutrition_plan(user["id"], data)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create nutrition plan"
        )
    
    return NutritionPlanResponse(
        id=plan["id"],
        user_id=plan["user_id"],
        is_active=plan["is_active"],
        nutrition_goal=plan.get("nutrition_goal"),
        dietary_restrictions=plan.get("dietary_restrictions"),
        meal_preferences=plan.get("meal_preferences"),
        cooking_time=plan.get("cooking_time"),
        budget=plan.get("budget"),
        target_calories=plan.get("target_calories"),
        target_proteins=plan.get("target_proteins"),
        target_fats=plan.get("target_fats"),
        target_carbs=plan.get("target_carbs"),
        created_at=plan.get("created_at")
    )
