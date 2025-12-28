from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user
from app.db import supabase_client
from .schemas import FeedbackCreateRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(data: FeedbackCreateRequest, user: dict = Depends(get_current_user)):
	payload = {
		"user_id": user["id"],
		"category": data.category,
		"message": data.message,
		"created_at": datetime.utcnow().isoformat(),
	}
	result = await supabase_client.insert("feedback", payload)
	if not result:
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save feedback")
	return FeedbackResponse(**result[0])


