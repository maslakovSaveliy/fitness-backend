from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from app.dependencies import get_current_user, get_current_paid_user
from .schemas import (
    MealCreate,
    MealResponse,
    MealListResponse,
    FoodAnalyzeRequest,
    FoodDescriptionRequest,
    FoodAnalyzeResponse,
    DailyNutritionStatsResponse,
    NutritionPlanCreate,
    NutritionPlanResponse,
    KBJURecommendations,
    NutritionPlanMenuResponse,
    DailyMenuStructured,
    DailyMenuStructuredResponse,
    WeekMenuResponse,
    ShoppingListRequest,
    ShoppingListResponse,
)
from .service import (
    get_user_meals,
    create_meal,
    analyze_food_photo,
    analyze_food_photo_with_history,
    analyze_food_description,
    get_daily_nutrition_stats,
    get_active_nutrition_plan,
    create_nutrition_plan,
    get_kbju_recommendations,
    create_daily_menu,
    create_weekly_menu,
    get_menu_by_day_of_week,
    get_week_menus,
    has_week_menu,
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
            meal_type=m.get("meal_type", "snack"),
            created_at=m.get("created_at")
        )
        for m in meals
    ]
    
    return MealListResponse(items=items, total=total)


@router.post("/meals", status_code=status.HTTP_201_CREATED)
async def add_meal(
    data: MealCreate,
    user: dict = Depends(get_current_paid_user)
):
    """Добавить прием пищи."""
    import logging
    logging.info(f"Creating meal: {data}")
    meal = await create_meal(user["id"], data)
    
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create meal"
        )
    
    # Return raw dict - skip Pydantic response validation
    return {
        "id": meal["id"],
        "user_id": meal["user_id"],
        "date": meal["date"],
        "description": meal["description"],
        "calories": meal.get("calories"),
        "proteins": meal.get("proteins"),
        "fats": meal.get("fats"),
        "carbs": meal.get("carbs"),
        "photo_url": meal.get("photo_url"),
        "meal_type": meal.get("meal_type", "snack"),
        "created_at": meal.get("created_at")
    }


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


@router.post("/meals/analyze-description", response_model=FoodAnalyzeResponse)
async def analyze_food_description_endpoint(
    data: FoodDescriptionRequest,
    user: dict = Depends(get_current_paid_user)
):
    """Анализировать описание еды через AI (без фото)."""
    result = await analyze_food_description(data.description)
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
    """Получить рекомендации по КБЖУ на сегодня. Использует targets из активного плана если есть."""
    from datetime import date as dt_date
    today = dt_date.today()
    
    stats = await get_daily_nutrition_stats(user["id"], today)
    
    # Get active plan to use its targets if available
    plan = await get_active_nutrition_plan(user["id"])
    recommendations = await get_kbju_recommendations(user, stats, plan)
    
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
    """Создать новый план питания и сгенерировать недельное меню."""
    plan = await create_nutrition_plan(user["id"], data, user)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create nutrition plan"
        )
    
    # Автоматически генерируем недельное меню для нового плана
    try:
        await create_weekly_menu(user, plan)
    except Exception as e:
        # Логируем ошибку но не прерываем создание плана
        import logging
        logging.error(f"Failed to generate weekly menu: {e}")
    
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
    """Legacy: Сгенерировать новый дневной рацион на основе активного плана (текстовый формат)."""
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


@router.get("/plans/active/menu/week", response_model=WeekMenuResponse)
async def get_week_menu_endpoint(user: dict = Depends(get_current_paid_user)):
    """Получить недельное меню для активного плана."""
    plan = await get_active_nutrition_plan(user["id"])
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active nutrition plan not found")

    menus = await get_week_menus(plan["id"])
    
    days: list[DailyMenuStructuredResponse | None] = [None] * 7
    for menu in menus:
        day_of_week = menu.get("day_of_week")
        if day_of_week is not None and 0 <= day_of_week < 7 and menu.get("menu_structured"):
            days[day_of_week] = DailyMenuStructuredResponse(
                id=menu["id"],
                plan_id=menu["plan_id"],
                day_of_week=day_of_week,
                menu_structured=DailyMenuStructured(**menu["menu_structured"]),
                created_at=menu.get("created_at"),
            )
    
    return WeekMenuResponse(
        plan_id=plan["id"],
        days=days,
        has_menu=any(d is not None for d in days),
    )


@router.get("/plans/active/menu/day/{day_of_week}", response_model=DailyMenuStructuredResponse | None)
async def get_day_menu_endpoint(
    day_of_week: int = Path(..., ge=0, le=6, description="День недели (0=Пн, 6=Вс)"),
    user: dict = Depends(get_current_paid_user),
):
    """Получить меню на конкретный день недели."""
    plan = await get_active_nutrition_plan(user["id"])
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active nutrition plan not found")

    menu = await get_menu_by_day_of_week(plan["id"], day_of_week)
    if not menu or not menu.get("menu_structured"):
        return None

    return DailyMenuStructuredResponse(
        id=menu["id"],
        plan_id=menu["plan_id"],
        day_of_week=menu.get("day_of_week"),
        menu_structured=DailyMenuStructured(**menu["menu_structured"]),
        created_at=menu.get("created_at"),
    )


@router.post("/plans/active/menu/generate-week", response_model=WeekMenuResponse, status_code=status.HTTP_201_CREATED)
async def generate_week_menu_endpoint(user: dict = Depends(get_current_paid_user)):
    """Сгенерировать недельное меню и сохранить."""
    plan = await get_active_nutrition_plan(user["id"])
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active nutrition plan not found")

    try:
        menus = await create_weekly_menu(user, plan)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    days: list[DailyMenuStructuredResponse | None] = [None] * 7
    for menu in menus:
        day_of_week = menu.get("day_of_week")
        if day_of_week is not None and 0 <= day_of_week < 7 and menu.get("menu_structured"):
            days[day_of_week] = DailyMenuStructuredResponse(
                id=menu["id"],
                plan_id=menu["plan_id"],
                day_of_week=day_of_week,
                menu_structured=DailyMenuStructured(**menu["menu_structured"]),
                created_at=menu.get("created_at"),
            )

    return WeekMenuResponse(
        plan_id=plan["id"],
        days=days,
        has_menu=True,
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

