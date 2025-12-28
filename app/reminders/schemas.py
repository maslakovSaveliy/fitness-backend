from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ReminderSettingsResponse(BaseModel):
	enabled: bool
	timezone: Optional[str] = None


class ReminderSettingsUpdateRequest(BaseModel):
	enabled: Optional[bool] = None
	timezone: Optional[str] = None


class ReminderRecord(BaseModel):
	id: str
	user_id: str
	enabled: bool
	timezone: Optional[str] = None
	created_at: Optional[datetime] = None
	updated_at: Optional[datetime] = None


