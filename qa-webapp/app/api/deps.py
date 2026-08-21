from typing import AsyncGenerator
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import SessionLocal
from app.models.models import User
from app.core.security import decode_access_token

class RequiresLoginException(Exception):
    """Exception khusus jika user belum login / token tidak valid."""
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection untuk menyediakan database session di setiap HTTP Request."""
    async with SessionLocal() as session:
        yield session

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Mengambil user yang sedang login berdasarkan HTTP-Only Cookie."""
    token = request.cookies.get("access_token")
    if not token:
        raise RequiresLoginException()
    
    # Hapus prefix "Bearer " jika ada
    if token.startswith("Bearer "):
        token = token.split(" ")[1]

    username = decode_access_token(token)
    if not username:
        raise RequiresLoginException()

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    
    if not user:
        raise RequiresLoginException()
        
    return user