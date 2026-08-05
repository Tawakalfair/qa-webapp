from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import SessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection untuk menyediakan database session di setiap HTTP Request."""
    async with SessionLocal() as session:
        yield session