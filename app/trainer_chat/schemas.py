from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TrainerChatSessionCreateRequest(BaseModel):
	original_workout_text: Optional[str] = None


class TrainerChatSessionResponse(BaseModel):
	id: str
	user_id: str
	status: str
	original_workout_text: Optional[str] = None
	updated_workout_text: Optional[str] = None
	created_at: Optional[datetime] = None


class TrainerChatMessageCreateRequest(BaseModel):
	text: str


class TrainerChatMessageResponse(BaseModel):
	id: str
	session_id: str
	role: str
	content: str
	created_at: Optional[datetime] = None


class TrainerChatSendMessageResponse(BaseModel):
	assistant_message: str


class TrainerChatFinishResponse(BaseModel):
	updated_workout_text: str


