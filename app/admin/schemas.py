from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AdminUserResponse(BaseModel):
	id: str
	telegram_id: int
	username: Optional[str] = None
	first_name: Optional[str] = None
	last_name: Optional[str] = None
	role: Optional[str] = None
	is_paid: bool = False
	paid_until: Optional[datetime] = None
	trial_expired: bool = False
	is_pro: bool = False
	supersets_enabled: bool = False
	custom_split_frequency: Optional[int] = None
	last_active_at: Optional[datetime] = None


class AdminUserListResponse(BaseModel):
	items: list[AdminUserResponse]
	total: int


class AdminUserUpdateRequest(BaseModel):
	role: Optional[str] = None
	is_paid: Optional[bool] = None
	paid_until: Optional[datetime] = None
	trial_expired: Optional[bool] = None
	is_pro: Optional[bool] = None
	supersets_enabled: Optional[bool] = None
	custom_split_frequency: Optional[int] = None

