import sys
import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy import update

from app.core.database import SessionLocal
from app.models.models import TestRun

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.core.config import settings
from app.api.deps import RequiresLoginException
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.media import router as media_router
from app.api.v1.export import router as export_router
from app.api.v1.scenarios import router as scenarios_router # 🟢 Include Scenarios Router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def cleanup_stuck_runs():
    """Reset any test runs left in PENDING/RUNNING status when the server restarts."""
    async with SessionLocal() as db:
        await db.execute(
            update(TestRun)
            .where(TestRun.status.in_(["PENDING", "RUNNING"]))
            .values(status="FAILED", error_log="Execution interrupted due to server restart/kill process.")
        )
        await db.commit()

@app.exception_handler(RequiresLoginException)
async def requires_login_exception_handler(request: Request, exc: RequiresLoginException):
    return RedirectResponse(url="/login", status_code=303)

# Register all Routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(media_router)
app.include_router(export_router)
app.include_router(scenarios_router) # 🟢 Register Scenarios Router