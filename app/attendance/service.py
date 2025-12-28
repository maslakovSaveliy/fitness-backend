from datetime import datetime, timedelta, date as dt_date
from app.db import supabase_client
from app.ai.prompts import WORKOUT_SPLITS, SPLIT_DESCRIPTIONS


def _parse_iso_datetime(value: str) -> datetime | None:
	"""
	Поведение максимально близко к боту:
	- основная попытка: datetime.fromisoformat(value)
	- fallback: поддержка Z-согласования
	"""
	try:
		return datetime.fromisoformat(value)
	except Exception:
		try:
			return datetime.fromisoformat(value.replace("Z", "+00:00"))
		except Exception:
			return None


def _should_use_supersets(user_data: dict) -> bool:
	# 1-в-1 с bot/attendance_tracker.py: если настройка задана — берём её.
	if "supersets_enabled" in user_data and isinstance(user_data.get("supersets_enabled"), bool):
		return bool(user_data["supersets_enabled"])

	workout_formats = str(user_data.get("workout_formats", "") or "").lower()
	superset_keywords = ["суперсет", "superset", "круговая", "circuit", "интенсив", "быстро"]
	avoid_keywords = ["классическая", "отдых", "медленно", "новичок"]

	has_superset_preference = any(keyword in workout_formats for keyword in superset_keywords)
	has_avoid_preference = any(keyword in workout_formats for keyword in avoid_keywords)

	if "классическая" in workout_formats:
		return False

	level = str(user_data.get("level", "") or "").lower()
	if level in ["новичок", "beginner"]:
		return has_superset_preference

	if has_avoid_preference:
		return False

	return has_superset_preference or level in ["средний", "продвинутый", "advanced"]


async def calculate_attendance(user: dict) -> dict:
	user_id = user["id"]
	days = 30
	cutoff_date = datetime.utcnow() - timedelta(days=days)

	workouts = await supabase_client.get(
		"workouts",
		{
			"user_id": f"eq.{user_id}",
			"select": "id,date",
			"order": "date.desc",
			"limit": "100",
		},
	)

	if not workouts:
		total_workouts = 0
		average_weekly = 0.0
		real_frequency = 0
		last_workout_date = None
	else:
		recent_workouts: list[dict] = []
		for w in workouts:
			date_value = w.get("date")
			if not isinstance(date_value, str):
				continue
			parsed = _parse_iso_datetime(date_value)
			if not parsed:
				continue
			if parsed >= cutoff_date:
				recent_workouts.append(w)

		total_workouts = len(recent_workouts)
		weeks_in_period = days / 7
		avg = (total_workouts / weeks_in_period) if weeks_in_period > 0 else 0.0
		average_weekly = round(avg, 1)
		real_frequency = min(5, max(1, round(avg))) if total_workouts > 0 else 0

		last_workout_date = None
		if recent_workouts:
			last_dt: datetime | None = None
			for w in recent_workouts:
				date_value = w.get("date")
				if not isinstance(date_value, str):
					continue
				parsed = _parse_iso_datetime(date_value)
				if not parsed:
					continue
				if (last_dt is None) or (parsed > last_dt):
					last_dt = parsed
			if last_dt is not None:
				last_workout_date = last_dt.date()

	custom_frequency = user.get("custom_split_frequency")
	is_custom_split = False
	custom_split_groups = None
	if isinstance(custom_frequency, int):
		custom_split_groups = WORKOUT_SPLITS.get(custom_frequency, WORKOUT_SPLITS[3])
		if custom_frequency != real_frequency:
			is_custom_split = True

	display_frequency = custom_frequency if is_custom_split else real_frequency
	recommended_split = SPLIT_DESCRIPTIONS.get(display_frequency, SPLIT_DESCRIPTIONS[3])
	recommended_split_groups = WORKOUT_SPLITS.get(display_frequency, WORKOUT_SPLITS[3])

	return {
		"real_frequency": real_frequency,
		"average_weekly": average_weekly,
		"total_workouts": total_workouts,
		"last_workout_date": last_workout_date,
		"recommended_split": recommended_split,
		"recommended_split_groups": recommended_split_groups,
		"custom_split_frequency": custom_frequency,
		"custom_split_groups": custom_split_groups,
		"is_custom_split": is_custom_split,
		"supersets_enabled": _should_use_supersets(user),
	}


