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
    meal_date = data.date or dt_date.today()
    
    meal_data = {
        "user_id": user_id,
        "date": meal_date.isoformat(),
        "description": data.description,
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


async def get_daily_nutrition_stats(
    user_id: str,
    date_filter: dt_date | None = None
) -> dict:
    target_date = date_filter or dt_date.today()
    
    stats = await supabase_client.get_one(
        "daily_nutrition_stats",
        {"user_id": f"eq.{user_id}", "date": f"eq.{target_date.isoformat()}"}
    )
    
    if stats:
        return stats
    
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


async def create_nutrition_plan(user_id: str, data: NutritionPlanCreate) -> dict:
    await supabase_client.update(
        "nutrition_plans",
        {"user_id": f"eq.{user_id}", "is_active": "eq.true"},
        {"is_active": False}
    )
    
    plan_data = {
        "user_id": user_id,
        "nutrition_goal": data.nutrition_goal,
        "dietary_restrictions": data.dietary_restrictions,
        "meal_preferences": data.meal_preferences,
        "cooking_time": data.cooking_time,
        "budget": data.budget,
        "is_active": True
    }
    
    result = await supabase_client.insert("nutrition_plans", plan_data)
    return result[0] if result else None


def calculate_kbju_targets(user: dict) -> dict:
    try:
        weight = float(user.get('weight') or 70)
        height = float(user.get('height') or 175)
        age = float(user.get('age') or 30)
        
        if user.get('gender') == 'М':
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161
    except (ValueError, TypeError):
        bmr = 1800
    
    activity_level = user.get('workouts_per_week') or 3
    if isinstance(activity_level, str):
        try:
            activity_level = int(activity_level)
        except ValueError:
            activity_level = 3
    
    if activity_level <= 1:
        activity_multiplier = 1.2
    elif activity_level <= 3:
        activity_multiplier = 1.375
    elif activity_level <= 5:
        activity_multiplier = 1.55
    else:
        activity_multiplier = 1.725
    
    tdee = bmr * activity_multiplier
    goal = (user.get('goal') or '').lower()
    
    if 'похудеть' in goal or 'сбросить' in goal or 'снижение' in goal:
        target_calories = tdee - 500
        protein_percent, fat_percent, carb_percent = 35, 25, 40
    elif 'набрать' in goal or 'массу' in goal or 'набор' in goal:
        target_calories = tdee + 300
        protein_percent, fat_percent, carb_percent = 30, 20, 50
    else:
        target_calories = tdee - 200
        protein_percent, fat_percent, carb_percent = 30, 25, 45
    
    return {
        "target_calories": int(target_calories),
        "target_proteins": int((target_calories * protein_percent / 100) / 4),
        "target_fats": int((target_calories * fat_percent / 100) / 9),
        "target_carbs": int((target_calories * carb_percent / 100) / 4)
    }


async def get_kbju_recommendations(user: dict, daily_stats: dict) -> dict:
    targets = calculate_kbju_targets(user)
    
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

