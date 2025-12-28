from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_admin_user
from .schemas import BroadcastCreateRequest, BroadcastResponse, BroadcastSendResponse
from .service import create_broadcast, send_broadcast

router = APIRouter(prefix="/admin/broadcasts", tags=["admin"])


@router.post("", response_model=BroadcastResponse, status_code=status.HTTP_201_CREATED)
async def create_broadcast_endpoint(
	data: BroadcastCreateRequest,
	admin: dict = Depends(get_current_admin_user),
):
	if data.audience not in ("all", "paid", "unpaid"):
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid audience")

	row = await create_broadcast(admin["id"], data.text, data.audience)
	if not row:
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create broadcast")
	return BroadcastResponse(**row)


@router.post("/{broadcast_id}/send", response_model=BroadcastSendResponse)
async def send_broadcast_endpoint(
	broadcast_id: str,
	admin: dict = Depends(get_current_admin_user),
):
	_ = admin
	# Fetch broadcast
	# Supabase REST filter
	from app.db import supabase_client
	broadcast = await supabase_client.get_one("broadcasts", {"id": f"eq.{broadcast_id}"})
	if not broadcast:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")

	queued = await send_broadcast(broadcast)
	return BroadcastSendResponse(queued=queued)


