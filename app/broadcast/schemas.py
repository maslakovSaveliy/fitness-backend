from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class BroadcastCreateRequest(BaseModel):
	text: str
	audience: str  # all | paid | unpaid


class BroadcastResponse(BaseModel):
	id: str
	created_by: str
	text: str
	audience: str
	status: str
	created_at: Optional[datetime] = None


class BroadcastSendResponse(BaseModel):
	queued: int

