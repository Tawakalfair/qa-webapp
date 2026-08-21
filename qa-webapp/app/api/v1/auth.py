from datetime import timedelta
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.models import User
from app.core.security import verify_password, create_access_token
from app.core.config import settings

router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Menampilkan halaman login."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Memvalidasi kredensial dan mengatur cookie sesi."""
    # 1. Cari user di database
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    # 2. Verifikasi password
    if not user or not verify_password(password, user.hashed_password):
        error_msg = "Username atau kata sandi salah!"
        return templates.TemplateResponse("login.html", {"request": request, "error": error_msg})

    # 3. Buat Token JWT
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # 4. Redirect ke dashboard dan simpan token di HttpOnly Cookie
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,  # Mencegah XSS (JavaScript tidak bisa membaca cookie ini)
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response

@router.post("/logout")
async def logout():
    """Menghapus cookie sesi."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response