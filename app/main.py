import sys
import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.core.config import settings
from app.api.deps import RequiresLoginException
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.media import router as media_router
from app.api.v1.export import router as export_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Tangkap Error Belum Login (Redirect ke halaman Login)
@app.exception_handler(RequiresLoginException)
async def requires_login_exception_handler(request: Request, exc: RequiresLoginException):
    return RedirectResponse(url="/login", status_code=303)

# Daftarkan semua Router
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(media_router)
app.include_router(export_router)