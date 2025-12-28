from pydantic import BaseModel
from typing import Optional
from datetime import date


class AttendanceStatsResponse(BaseModel):
	real_frequency: int
	average_weekly: float
	total_workouts: int
	last_workout_date: Optional[date] = None
	recommended_split: str
	recommended_split_groups: list[str]
	custom_split_frequency: Optional[int] = None
	custom_split_groups: Optional[list[str]] = None
	is_custom_split: bool
	supersets_enabled: bool


