from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.dependencies import get_current_admin_user
from app.db import supabase_client
from .schemas import AdminUserListResponse, AdminUserResponse, AdminUserUpdateRequest

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
	limit: int = Query(50, ge=1, le=200),
	offset: int = Query(0, ge=0),
	_admin: dict = Depends(get_current_admin_user),
):
	users = await supabase_client.get(
		"users",
		{"order": "created_at.desc", "limit": str(limit), "offset": str(offset)},
	)
	total_rows = await supabase_client.get("users", {"select": "id"})
	total = len(total_rows) if total_rows else 0
	items = [AdminUserResponse(**u) for u in users]
	return AdminUserListResponse(items=items, total=total)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
	user_id: str,
	data: AdminUserUpdateRequest,
	_admin: dict = Depends(get_current_admin_user),
):
	update_data = data.model_dump(exclude_none=True)
	if not update_data:
		user = await supabase_client.get_one("users", {"id": f"eq.{user_id}"})
		if not user:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
		return AdminUserResponse(**user)

	if "paid_until" in update_data and update_data["paid_until"] is not None:
		update_data["paid_until"] = update_data["paid_until"].isoformat()

	result = await supabase_client.update("users", {"id": f"eq.{user_id}"}, update_data)
	if not result:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
	return AdminUserResponse(**result[0])


