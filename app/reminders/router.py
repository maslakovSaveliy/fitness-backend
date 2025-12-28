from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from .schemas import ReminderSettingsResponse, ReminderSettingsUpdateRequest
from .service import get_or_create_user_reminder, update_user_reminder

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/me", response_model=ReminderSettingsResponse)
async def get_my_reminders(user: dict = Depends(get_current_user)):
	row = await get_or_create_user_reminder(user["id"])
	return ReminderSettingsResponse(enabled=bool(row.get("enabled", True)), timezone=row.get("timezone"))


@router.patch("/me", response_model=ReminderSettingsResponse)
async def update_my_reminders(data: ReminderSettingsUpdateRequest, user: dict = Depends(get_current_user)):
	row = await update_user_reminder(user["id"], data)
	return ReminderSettingsResponse(enabled=bool(row.get("enabled", True)), timezone=row.get("timezone"))


