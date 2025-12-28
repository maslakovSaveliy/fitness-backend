from fastapi import APIRouter, Depends
from app.dependencies import get_current_paid_user
from .schemas import AttendanceStatsResponse
from .service import calculate_attendance

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("/stats", response_model=AttendanceStatsResponse)
async def get_attendance_stats(user: dict = Depends(get_current_paid_user)):
	"""Статистика посещаемости и сплитов как в боте."""
	stats = await calculate_attendance(user)
	return AttendanceStatsResponse(**stats)


