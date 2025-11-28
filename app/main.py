from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.auth import auth_router
from app.users import users_router
from app.workouts import workouts_router
from app.nutrition import nutrition_router

settings = get_settings()

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

