from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TrialStatusResponse(BaseModel):
	trial_expired: bool
	paid_until: Optional[datetime] = None
	is_paid: bool


class TrialMarkExpiredRequest(BaseModel):
	trial_expired: bool = True


