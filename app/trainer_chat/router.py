from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user, get_current_paid_user
from .schemas import (
	TrainerChatSessionCreateRequest,
	TrainerChatSessionResponse,
	TrainerChatMessageCreateRequest,
	TrainerChatSendMessageResponse,
	TrainerChatFinishResponse,
)
from .service import (
	create_session,
	get_session,
	send_trainer_message,
	finish_trainer_chat,
	revert_trainer_chat,
)

router = APIRouter(prefix="/trainer-chat", tags=["trainer-chat"])


@router.post("/sessions", response_model=TrainerChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_trainer_chat_session(
	data: TrainerChatSessionCreateRequest,
	user: dict = Depends(get_current_paid_user),
):
	session = await create_session(user, data.original_workout_text)
	if not session:
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create session")
	return TrainerChatSessionResponse(**session)


@router.post("/sessions/{session_id}/messages", response_model=TrainerChatSendMessageResponse)
async def send_message(
	session_id: str,
	data: TrainerChatMessageCreateRequest,
	user: dict = Depends(get_current_paid_user),
):
	session = await get_session(session_id, user["id"])
	if not session:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

	answer = await send_trainer_message(session, user, data.text)
	return TrainerChatSendMessageResponse(assistant_message=answer)


@router.post("/sessions/{session_id}/finish", response_model=TrainerChatFinishResponse)
async def finish_session(
	session_id: str,
	user: dict = Depends(get_current_paid_user),
):
	session = await get_session(session_id, user["id"])
	if not session:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

	updated = await finish_trainer_chat(session, user)
	return TrainerChatFinishResponse(updated_workout_text=updated)


@router.post("/sessions/{session_id}/revert", response_model=TrainerChatFinishResponse)
async def revert_session(
	session_id: str,
	user: dict = Depends(get_current_paid_user),
):
	session = await get_session(session_id, user["id"])
	if not session:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

	original = await revert_trainer_chat(session, user)
	return TrainerChatFinishResponse(updated_workout_text=original)


@router.get("/sessions/{session_id}", response_model=TrainerChatSessionResponse)
async def get_session_info(
	session_id: str,
	user: dict = Depends(get_current_user),
):
	session = await get_session(session_id, user["id"])
	if not session:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
	return TrainerChatSessionResponse(**session)


