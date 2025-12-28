from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.dependencies import get_current_user, get_current_paid_user
from .schemas import (
    MealCreate,
    MealResponse,
    MealListResponse,
    FoodAnalyzeRequest,
    FoodAnalyzeResponse,
    DailyNutritionStatsResponse,
    NutritionPlanCreate,
    NutritionPlanResponse,
    KBJURecommendations,
    NutritionPlanMenuResponse,
    ShoppingListRequest,
    ShoppingListResponse,
)
from .service import (
    get_user_meals,
    create_meal,
    analyze_food_photo,
    analyze_food_photo_with_history,
    get_daily_nutrition_stats,
    get_active_nutrition_plan,
    create_nutrition_plan,
    get_kbju_recommendations,
    create_daily_menu,
    get_menu_by_id,
    generate_shopping_list,
)

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


@router.get("/meals", response_model=MealListResponse)
async def list_meals(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    date_filter: date | None = Query(None, alias="date"),
    user: dict = Depends(get_current_user)
):
    """Получить список приемов пищи."""
    meals, total = await get_user_meals(user["id"], limit, offset, date_filter)
    
    items = [
        MealResponse(
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
        for m in meals
    ]
    
    return MealListResponse(items=items, total=total)


@router.post("/meals", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
async def add_meal(
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
    
    return MealResponse(
        id=meal["id"],
        user_id=meal["user_id"],
        date=meal["date"],
        description=meal["description"],
        calories=meal.get("calories"),
        proteins=meal.get("proteins"),
        fats=meal.get("fats"),
        carbs=meal.get("carbs"),
        photo_url=meal.get("photo_url"),
        created_at=meal.get("created_at")
    )


@router.post("/meals/analyze", response_model=FoodAnalyzeResponse)
async def analyze_food(
    data: FoodAnalyzeRequest,
    user: dict = Depends(get_current_paid_user)
):
    """Анализировать фото еды через AI."""
    if data.clarifications:
        result = await analyze_food_photo_with_history(
            data.image_url,
            data.clarifications,
            initial_description=data.initial_description,
        )
    else:
        result = await analyze_food_photo(data.image_url, data.clarification)
    return result


@router.get("/stats/today", response_model=DailyNutritionStatsResponse)
async def get_today_stats(user: dict = Depends(get_current_user)):
    """Получить статистику питания за сегодня."""
    from datetime import date as dt_date
    today = dt_date.today()
    
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
async def get_date_stats(
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
async def get_recommendations(user: dict = Depends(get_current_user)):
    """Получить рекомендации по КБЖУ на сегодня."""
    from datetime import date as dt_date
    today = dt_date.today()
    
    stats = await get_daily_nutrition_stats(user["id"], today)
    recommendations = await get_kbju_recommendations(user, stats)
    
    return KBJURecommendations(**recommendations)


@router.get("/plans/active", response_model=NutritionPlanResponse | None)
async def get_active_plan(user: dict = Depends(get_current_user)):
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
async def create_plan(
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


@router.get("/plans/active/menu", response_model=NutritionPlanMenuResponse)
async def get_active_plan_menu(user: dict = Depends(get_current_paid_user)):
    """Сгенерировать новый дневной рацион на основе активного плана (как в боте)."""
    plan = await get_active_nutrition_plan(user["id"])
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active nutrition plan not found")

    menu = await create_daily_menu(user, plan)
    return NutritionPlanMenuResponse(
        id=menu["id"],
        plan_id=menu["plan_id"],
        date=menu["date"],
        menu_text=menu["menu_text"],
        created_at=menu.get("created_at"),
    )


@router.post("/plans/active/shopping-list", response_model=ShoppingListResponse)
async def get_shopping_list(
    data: ShoppingListRequest,
    user: dict = Depends(get_current_paid_user),
):
    """Сгенерировать список продуктов по дневному рациону (menu_id или menu_text)."""
    plan = await get_active_nutrition_plan(user["id"])
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active nutrition plan not found")

    menu_text: str | None = data.menu_text
    if not menu_text and data.menu_id:
        menu = await get_menu_by_id(data.menu_id, plan["id"])
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
        menu_text = menu.get("menu_text")

    if not menu_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="menu_text or menu_id is required")

    shopping_list = await generate_shopping_list(menu_text)
    return ShoppingListResponse(shopping_list=shopping_list)

