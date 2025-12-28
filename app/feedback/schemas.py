from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FeedbackCreateRequest(BaseModel):
	category: Optional[str] = None
	message: str


class FeedbackResponse(BaseModel):
	id: str
	user_id: str
	category: Optional[str] = None
	message: str
	created_at: Optional[datetime] = None


