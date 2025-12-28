from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.workouts.schemas import WorkoutResponse

class TrainerChatSessionCreateRequest(BaseModel):
	workout_id: str


class TrainerChatSessionResponse(BaseModel):
	id: str
	user_id: str
	status: str
	workout_id: Optional[str] = None
	original_workout_text: Optional[str] = None
	updated_workout_text: Optional[str] = None
	original_workout_details: Optional[object] = None
	updated_workout_details: Optional[object] = None
	created_at: Optional[datetime] = None
	updated_at: Optional[datetime] = None


class TrainerChatSessionCreateResponse(BaseModel):
	session: TrainerChatSessionResponse
	initial_assistant_message: str


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
	workout: WorkoutResponse


