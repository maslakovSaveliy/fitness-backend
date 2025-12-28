from fastapi import APIRouter, Depends
from fastapi.responses import Response
from app.dependencies import get_current_paid_user
from .service import export_workouts_xlsx, export_nutrition_xlsx

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/workouts.xlsx")
async def export_workouts(user: dict = Depends(get_current_paid_user)):
	data = await export_workouts_xlsx(user["id"])
	return Response(
		content=data,
		media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		headers={"Content-Disposition": 'attachment; filename="workout_history.xlsx"'},
	)


@router.get("/nutrition.xlsx")
async def export_nutrition(user: dict = Depends(get_current_paid_user)):
	data = await export_nutrition_xlsx(user["id"])
	return Response(
		content=data,
		media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		headers={"Content-Disposition": 'attachment; filename="nutrition_history.xlsx"'},
	)


