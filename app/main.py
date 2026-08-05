import sys
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.core.config import settings
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.media import router as media_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(dashboard_router)
app.include_router(media_router)