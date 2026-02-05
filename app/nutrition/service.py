import json
from datetime import date as dt_date
from app.db import supabase_client
from app.ai import ai_service
from .schemas import MealCreate, NutritionPlanCreate, FoodAnalyzeResponse


async def get_user_meals(
    user_id: str,
    limit: int = 10,
    offset: int = 0,
    date_filter: dt_date | None = None
) -> tuple[list[dict], int]:
    params = {
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset)
    }
    
    if date_filter:
        params["date"] = f"eq.{date_filter.isoformat()}"
    
    meals = await supabase_client.get("meals", params)
    
    count_params = {"user_id": f"eq.{user_id}", "select": "id"}
    if date_filter:
        count_params["date"] = f"eq.{date_filter.isoformat()}"
    
    count_result = await supabase_client.get("meals", count_params)
    total = len(count_result) if count_result else 0
    
    return meals, total


async def create_meal(user_id: str, data: MealCreate) -> dict:
    # Parse date from string or use today
    if data.date:
        if isinstance(data.date, str):
            meal_date = dt_date.fromisoformat(data.date)
        else:
            meal_date = data.date
    else:
        meal_date = dt_date.today()
    
    meal_data = {
        "user_id": user_id,
        "date": meal_date.isoformat(),
        "description": data.description,
        "meal_type": data.meal_type or "user",  # Default to "user" for manual entries
    }
    
    if data.calories is not None:
        meal_data["calories"] = data.calories
    if data.proteins is not None:
        meal_data["proteins"] = data.proteins
    if data.fats is not None:
        meal_data["fats"] = data.fats
    if data.carbs is not None:
        meal_data["carbs"] = data.carbs
    if data.photo_url:
        meal_data["photo_url"] = data.photo_url
    
    result = await supabase_client.insert("meals", meal_data)
    
    if result:
        await update_daily_nutrition_stats(user_id, meal_date)
    
    return result[0] if result else None


async def analyze_food_photo(
    image_url: str,
    clarification: str | None = None
) -> FoodAnalyzeResponse:
    if clarification:
        response = await ai_service.analyze_food_with_clarification(image_url, clarification)
    else:
        response = await ai_service.analyze_food_photo(image_url)
    
    json_start = response.find('{')
    json_end = response.rfind('}')
    
    if json_start != -1 and json_end != -1 and json_end > json_start:
        try:
            data = json.loads(response[json_start:json_end+1])
            return FoodAnalyzeResponse(
                description=data.get("description", "Блюдо"),
                calories=data.get("calories"),
                proteins=data.get("proteins"),
                fats=data.get("fats"),
                carbs=data.get("carbs")
            )
        except json.JSONDecodeError:
            pass
    
    return FoodAnalyzeResponse(description="Не удалось распознать блюдо")


async def analyze_food_photo_with_history(
    image_url: str,
    clarifications: list[str],
    initial_description: str | None = None,
) -> FoodAnalyzeResponse:
    # 1-в-1 с bot/calories.py:process_calories_clarification
    initial_desc = (initial_description or "").strip() or "Фото еды"
    prompt_parts: list[str] = [f'Исходное описание: "{initial_desc}".']
    for idx, clar in enumerate(clarifications):
        prompt_parts.append(f'Уточнение {idx + 1}: "{clar}".')
    prompt_parts.append("Уточни результат, учитывая все детали выше. Верни JSON с описанием, калориями и БЖУ.")
    combined = "\n".join(prompt_parts)
    return await analyze_food_photo(image_url, combined)


async def analyze_food_description(description: str) -> FoodAnalyzeResponse:
    """Analyze food from text description only (no photo)."""
    response = await ai_service.analyze_food_description(description)
    
    json_start = response.find('{')
    json_end = response.rfind('}')
    
    if json_start != -1 and json_end != -1 and json_end > json_start:
        try:
            data = json.loads(response[json_start:json_end+1])
            return FoodAnalyzeResponse(
                description=data.get("description", description),
                calories=data.get("calories"),
                proteins=data.get("proteins"),
                fats=data.get("fats"),
                carbs=data.get("carbs")
            )
        except json.JSONDecodeError:
            pass
    
    return FoodAnalyzeResponse(description=description)


async def get_daily_nutrition_stats(
    user_id: str,
    date_filter: dt_date | None = None
) -> dict:
    """Get nutrition stats for a specific date. Always calculates from actual meals."""
    target_date = date_filter or dt_date.today()
    
    # Always calculate from meals table to ensure accuracy
    return await update_daily_nutrition_stats(user_id, target_date)


async def update_daily_nutrition_stats(user_id: str, date_filter: dt_date) -> dict:
    meals = await supabase_client.get(
        "meals",
        {
            "user_id": f"eq.{user_id}",
            "date": f"eq.{date_filter.isoformat()}",
            "select": "calories,proteins,fats,carbs"
        }
    )
    
    total_calories = 0
    total_proteins = 0
    total_fats = 0
    total_carbs = 0
    
    if meals:
        for meal in meals:
            total_calories += meal.get("calories") or 0
            total_proteins += meal.get("proteins") or 0
            total_fats += meal.get("fats") or 0
            total_carbs += meal.get("carbs") or 0
    
    stats_data = {
        "user_id": user_id,
        "date": date_filter.isoformat(),
        "total_calories": int(total_calories),
        "total_proteins": int(total_proteins),
        "total_fats": int(total_fats),
        "total_carbs": int(total_carbs),
        "meals_count": len(meals) if meals else 0
    }
    
    existing = await supabase_client.get_one(
        "daily_nutrition_stats",
        {"user_id": f"eq.{user_id}", "date": f"eq.{date_filter.isoformat()}"}
    )
    
    if existing:
        result = await supabase_client.update(
            "daily_nutrition_stats",
            {"user_id": f"eq.{user_id}", "date": f"eq.{date_filter.isoformat()}"},
            stats_data
        )
    else:
        result = await supabase_client.insert("daily_nutrition_stats", stats_data)
    
    return result[0] if result else stats_data


async def get_active_nutrition_plan(user_id: str) -> dict | None:
    return await supabase_client.get_one(
        "nutrition_plans",
        {
            "user_id": f"eq.{user_id}",
            "is_active": "eq.true",
            "order": "created_at.desc",
            "limit": "1"
        }
    )


async def create_nutrition_plan(user_id: str, data: NutritionPlanCreate, user: dict) -> dict:
    """Create nutrition plan with formula-based KBJU targets."""
    await supabase_client.update(
        "nutrition_plans",
        {"user_id": f"eq.{user_id}", "is_active": "eq.true"},
        {"is_active": False}
    )
    
    # Calculate KBJU targets using proven formula
    targets = calculate_kbju_targets(user, data.nutrition_goal)
    
    plan_data = {
        "user_id": user_id,
        "nutrition_goal": data.nutrition_goal,
        "dietary_restrictions": data.dietary_restrictions,
        "meal_preferences": data.meal_preferences,
        "cooking_time": data.cooking_time,
        "budget": data.budget,
        "is_active": True,
        "target_calories": targets["target_calories"],
        "target_proteins": targets["target_proteins"],
        "target_fats": targets["target_fats"],
        "target_carbs": targets["target_carbs"],
    }
    
    result = await supabase_client.insert("nutrition_plans", plan_data)
    return result[0] if result else None


async def create_daily_menu(user: dict, plan: dict) -> dict:
    """Legacy function for text-based menu generation."""
    from datetime import date as dt_date_today
    today = dt_date_today.today()
    menu_text = await ai_service.generate_daily_menu(user, plan)

    payload = {
        "plan_id": plan["id"],
        "date": today.isoformat(),
        "menu_text": menu_text,
    }
    result = await supabase_client.insert("nutrition_plan_menus", payload)
    return result[0] if result else {"id": "", **payload}


async def create_weekly_menu(user: dict, plan: dict) -> list[dict]:
    """Generate and save structured JSON menu for 7 days."""
    weekly_menus = await ai_service.generate_weekly_menu_structured(user, plan)
    
    results: list[dict] = []
    for day_menu in weekly_menus:
        day_of_week = day_menu.get("day_of_week", 0)
        
        payload = {
            "plan_id": plan["id"],
            "day_of_week": day_of_week,
            "menu_text": "",
            "menu_structured": json.dumps(day_menu),
        }
        
        try:
            result = await supabase_client.insert("nutrition_plan_menus", payload)
            if result:
                menu_record = result[0]
                menu_record["menu_structured"] = day_menu
                results.append(menu_record)
            else:
                results.append({"id": "", **payload, "menu_structured": day_menu})
        except Exception:
            results.append({"id": "", **payload, "menu_structured": day_menu})
    
    return results


async def get_menu_by_day_of_week(plan_id: str, day_of_week: int) -> dict | None:
    """Get menu for specific day of week (0=Monday, 6=Sunday)."""
    try:
        menu = await supabase_client.get_one(
            "nutrition_plan_menus",
            {
                "plan_id": f"eq.{plan_id}",
                "day_of_week": f"eq.{day_of_week}",
                "order": "created_at.desc",
                "limit": "1",
            }
        )
    except Exception:
        return None
    
    if menu and menu.get("menu_structured"):
        if isinstance(menu["menu_structured"], str):
            try:
                menu["menu_structured"] = json.loads(menu["menu_structured"])
            except json.JSONDecodeError:
                menu["menu_structured"] = None
    
    return menu


async def get_week_menus(plan_id: str) -> list[dict]:
    """Get all 7 day menus for the plan."""
    try:
        menus = await supabase_client.get(
            "nutrition_plan_menus",
            {
                "plan_id": f"eq.{plan_id}",
                "order": "day_of_week.asc",
            }
        )
    except Exception:
        return []
    
    result: list[dict] = []
    for menu in menus:
        if menu.get("menu_structured"):
            if isinstance(menu["menu_structured"], str):
                try:
                    menu["menu_structured"] = json.loads(menu["menu_structured"])
                except json.JSONDecodeError:
                    menu["menu_structured"] = None
        result.append(menu)
    
    return result


async def has_week_menu(plan_id: str) -> bool:
    """Check if weekly menu exists for the plan."""
    try:
        menus = await supabase_client.get(
            "nutrition_plan_menus",
            {
                "plan_id": f"eq.{plan_id}",
                "select": "id",
                "limit": "1",
            }
        )
        return len(menus) > 0
    except Exception:
        return False


async def get_menu_by_id(menu_id: str, plan_id: str) -> dict | None:
    return await supabase_client.get_one(
        "nutrition_plan_menus",
        {"id": f"eq.{menu_id}", "plan_id": f"eq.{plan_id}"},
    )


async def generate_shopping_list(menu_text: str) -> str:
    return await ai_service.generate_shopping_list(menu_text)


def calculate_kbju_targets(user: dict, nutrition_goal: str | None = None) -> dict:
    """
    Calculate KBJU targets based on user data and nutrition goal.
    
    Uses Mifflin-St Jeor formula for BMR and evidence-based macro recommendations.
    
    Args:
        user: User profile data (weight, height, age, gender, workouts_per_week)
        nutrition_goal: Goal from nutrition plan brief (e.g. "Похудеть", "Набрать массу")
    """
    # Parse user data with defaults
    try:
        weight = float(user.get('weight') or 70)
        height = float(user.get('height') or 170)
        age = float(user.get('age') or 30)
    except (ValueError, TypeError):
        weight = 70
        height = 170
        age = 30
    
    is_male = user.get('gender') == 'М'
    
    # BMR by Mifflin-St Jeor formula
    if is_male:
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    # Activity multiplier based on workouts per week
    activity_level = user.get('workouts_per_week') or 3
    if isinstance(activity_level, str):
        try:
            activity_level = int(activity_level)
        except ValueError:
            activity_level = 3
    
    if activity_level <= 1:
        activity_multiplier = 1.2      # Sedentary
    elif activity_level <= 2:
        activity_multiplier = 1.375    # Light activity
    elif activity_level <= 4:
        activity_multiplier = 1.55     # Moderate activity
    else:
        activity_multiplier = 1.725    # Very active
    
    tdee = bmr * activity_multiplier
    
    # Parse goal
    goal = (nutrition_goal or user.get('goal') or '').lower()
    
    # Scientific recommendations for macros:
    # - Protein: 1.4-1.8 g/kg for most people, up to 2.0 g/kg only for athletes on hard deficit
    # - Fat: 0.7-1.0 g/kg minimum for hormonal health
    # - Carbs: remaining calories
    
    if 'похудеть' in goal or 'сбросить' in goal or 'снижение' in goal or 'похудение' in goal or 'дефицит' in goal:
        # Weight loss: 400-500 kcal deficit, higher protein to preserve muscle
        calorie_adjustment = -450
        protein_per_kg = 1.8
        fat_per_kg = 0.8
    elif 'набрать' in goal or 'массу' in goal or 'набор' in goal or 'масса' in goal or 'профицит' in goal:
        # Muscle gain: 250-350 kcal surplus
        calorie_adjustment = 300
        protein_per_kg = 1.6
        fat_per_kg = 1.0
    elif 'поддерж' in goal or 'форм' in goal or 'рекомпозиц' in goal:
        # Maintenance
        calorie_adjustment = 0
        protein_per_kg = 1.5
        fat_per_kg = 0.9
    else:
        # Default: slight deficit for health
        calorie_adjustment = -200
        protein_per_kg = 1.5
        fat_per_kg = 0.85
    
    target_calories = tdee + calorie_adjustment
    
    # Minimum calories for health (prevent too low values)
    min_calories = 1200 if not is_male else 1500
    target_calories = max(min_calories, target_calories)
    
    # Calculate macros from weight
    target_proteins = int(weight * protein_per_kg)
    target_fats = int(weight * fat_per_kg)
    
    # Carbs = remaining calories
    protein_calories = target_proteins * 4
    fat_calories = target_fats * 9
    remaining_calories = target_calories - protein_calories - fat_calories
    target_carbs = max(80, int(remaining_calories / 4))  # Minimum 80g carbs for brain function
    
    # Recalculate total calories to match actual macros
    actual_calories = protein_calories + fat_calories + (target_carbs * 4)
    
    return {
        "target_calories": int(actual_calories),
        "target_proteins": target_proteins,
        "target_fats": target_fats,
        "target_carbs": target_carbs
    }


async def get_kbju_recommendations(user: dict, daily_stats: dict, plan: dict | None = None) -> dict:
    """
    Get KBJU recommendations for today.
    
    Uses targets from active nutrition plan if available,
    otherwise calculates from user profile.
    """
    # Use targets from plan if available, otherwise calculate
    if plan and plan.get('target_calories'):
        targets = {
            'target_calories': plan['target_calories'],
            'target_proteins': plan.get('target_proteins', 100),
            'target_fats': plan.get('target_fats', 70),
            'target_carbs': plan.get('target_carbs', 250),
        }
    else:
        # Calculate from user profile with nutrition_goal if plan exists
        nutrition_goal = plan.get('nutrition_goal') if plan else None
        targets = calculate_kbju_targets(user, nutrition_goal)
    
    current_calories = daily_stats.get('total_calories', 0) or 0
    current_proteins = daily_stats.get('total_proteins', 0) or 0
    current_fats = daily_stats.get('total_fats', 0) or 0
    current_carbs = daily_stats.get('total_carbs', 0) or 0
    
    remaining_calories = max(0, targets['target_calories'] - current_calories)
    remaining_proteins = max(0, targets['target_proteins'] - current_proteins)
    remaining_fats = max(0, targets['target_fats'] - current_fats)
    remaining_carbs = max(0, targets['target_carbs'] - current_carbs)
    
    recommendations = []
    
    if current_calories >= targets['target_calories'] * 1.1:
        recommendations.append("⚠️ Вы превысили дневную норму калорий")
    elif current_calories >= targets['target_calories']:
        recommendations.append("✅ Достигнута дневная норма калорий")
    elif remaining_calories < 200:
        recommendations.append(f"🎯 Осталось {remaining_calories:.0f} ккал до нормы")
    else:
        recommendations.append(f"📈 Нужно еще {remaining_calories:.0f} ккал")
    
    if remaining_proteins > 20:
        recommendations.append(f"🥩 Белки: нужно еще {remaining_proteins:.0f} г")
    
    if remaining_fats > 15:
        recommendations.append(f"🥑 Жиры: нужно еще {remaining_fats:.0f} г")
    
    if remaining_carbs > 30:
        recommendations.append(f"🍞 Углеводы: нужно еще {remaining_carbs:.0f} г")
    
    return {
        **targets,
        "remaining_calories": remaining_calories,
        "remaining_proteins": remaining_proteins,
        "remaining_fats": remaining_fats,
        "remaining_carbs": remaining_carbs,
        "recommendations": recommendations
    }

