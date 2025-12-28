import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.auth import auth_router
from app.users import users_router
from app.workouts import workouts_router
from app.nutrition import nutrition_router
from app.trainer_chat import trainer_chat_router
from app.media import media_router
from app.attendance import attendance_router
from app.export import export_router
from app.reminders import reminders_router
from app.broadcast import broadcast_router
from app.reminders.scheduler import start_scheduler
from app.feedback import feedback_router
from app.admin import admin_router
from app.trial import trial_router

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="Fitness Mini App API",
    description="Backend API for Fitness Telegram Mini App",
    version="1.0.0",
    debug=settings.debug
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(workouts_router)
app.include_router(nutrition_router)
app.include_router(trainer_chat_router)
app.include_router(media_router)
app.include_router(attendance_router)
app.include_router(export_router)
app.include_router(reminders_router)
app.include_router(broadcast_router)
app.include_router(feedback_router)
app.include_router(admin_router)
app.include_router(trial_router)

_scheduler = None


@app.on_event("startup")
async def _startup_scheduler():
	global _scheduler
	if _scheduler is None:
		_scheduler = start_scheduler()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "app": "Fitness Mini App API",
        "version": "1.0.0",
        "docs": "/docs"
    }

