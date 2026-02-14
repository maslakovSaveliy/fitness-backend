import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_user, get_current_paid_user
from .schemas import (
    TrainerChatSessionCreateRequest,
    TrainerChatSessionResponse,
    TrainerChatSessionCreateResponse,
    TrainerChatMessageCreateRequest,
    TrainerChatSendMessageResponse,
    TrainerChatFinishResponse,
)
from .service import (
    create_session,
    get_session,
    send_trainer_message,
    send_trainer_message_stream,
    finish_trainer_chat,
    revert_trainer_chat,
)

router = APIRouter(prefix="/trainer-chat", tags=["trainer-chat"])


@router.post("/sessions", response_model=TrainerChatSessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_trainer_chat_session(
    data: TrainerChatSessionCreateRequest,
    user: dict = Depends(get_current_paid_user),
):
    try:
        session, initial_message = await create_session(user, data.workout_id)
    except httpx.HTTPStatusError as e:
        detail: object
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "supabase_request_failed",
                "hint": "Проверь, что применены scripts/supabase/001_trainer_chat.sql и 007_trainer_chat_workout_link.sql в Supabase SQL Editor",
                "supabase": detail,
            },
        )
    if not session or not initial_message:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create session")
    return TrainerChatSessionCreateResponse(
        session=TrainerChatSessionResponse(**session),
        initial_assistant_message=initial_message,
    )


@router.post("/sessions/{session_id}/messages", response_model=TrainerChatSendMessageResponse)
async def send_message(
    session_id: str,
    data: TrainerChatMessageCreateRequest,
    user: dict = Depends(get_current_paid_user),
):
    """Non-streaming fallback endpoint."""
    session = await get_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    answer = await send_trainer_message(session, user, data.text)
    return TrainerChatSendMessageResponse(assistant_message=answer)


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    data: TrainerChatMessageCreateRequest,
    user: dict = Depends(get_current_paid_user),
):
    """SSE streaming endpoint — text chunks arrive as they are generated."""
    session = await get_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    async def event_generator():
        try:
            async for chunk in send_trainer_message_stream(session, user, data.text):
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/finish", response_model=TrainerChatFinishResponse)
async def finish_session(
    session_id: str,
    user: dict = Depends(get_current_paid_user),
):
    session = await get_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    workout = await finish_trainer_chat(session, user)
    if not workout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update workout")
    return TrainerChatFinishResponse(workout=workout)


@router.post("/sessions/{session_id}/revert", response_model=TrainerChatFinishResponse)
async def revert_session(
    session_id: str,
    user: dict = Depends(get_current_paid_user),
):
    session = await get_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    workout = await revert_trainer_chat(session, user)
    if not workout:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to revert workout")
    return TrainerChatFinishResponse(workout=workout)


@router.get("/sessions/{session_id}", response_model=TrainerChatSessionResponse)
async def get_session_info(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return TrainerChatSessionResponse(**session)
