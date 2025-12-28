from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.db import supabase_client
from .schemas import TrialStatusResponse, TrialMarkExpiredRequest

router = APIRouter(prefix="/trial", tags=["trial"])


@router.get("/status", response_model=TrialStatusResponse)
async def get_trial_status(user: dict = Depends(get_current_user)):
	paid_until = user.get("paid_until")
	return TrialStatusResponse(
		trial_expired=bool(user.get("trial_expired", False)),
		paid_until=paid_until,
		is_paid=bool(paid_until),
	)


@router.post("/mark-expired", response_model=TrialStatusResponse)
async def mark_trial_expired(
	data: TrialMarkExpiredRequest,
	user: dict = Depends(get_current_user),
):
	updated = await supabase_client.update(
		"users",
		{"id": f"eq.{user['id']}"},
		{"trial_expired": bool(data.trial_expired)},
	)
	row = updated[0] if updated else user
	paid_until = row.get("paid_until")
	return TrialStatusResponse(
		trial_expired=bool(row.get("trial_expired", False)),
		paid_until=paid_until,
		is_paid=bool(paid_until),
	)


