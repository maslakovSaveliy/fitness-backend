from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from app.dependencies import get_current_paid_user
from .schemas import TranscribeResponse
from .service import transcribe_audio

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_endpoint(
	file: UploadFile = File(...),
	_user: dict = Depends(get_current_paid_user),
):
	try:
		data = await file.read()
		text = await transcribe_audio(data, file.filename or "audio.wav")
		return TranscribeResponse(text=text)
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to transcribe audio",
		)


