import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "QA Automata"
    PROJECT_VERSION: str = "2.0.0"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./qa_database.db"
    
    # Media Storage
    VIDEO_DIR: str = "static/videos"
    SCREENSHOT_DIR: str = "static/screenshots"

    # JWT Authentication
    SECRET_KEY: str = "super-rahasia-ganti-ini-di-production-nanti"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # Token & Cookie berlaku 7 hari

    class Config:
        env_file = ".env"

settings = Settings()

# Pastikan folder penyimpanan media terbuat
os.makedirs(settings.VIDEO_DIR, exist_ok=True)
os.makedirs(settings.SCREENSHOT_DIR, exist_ok=True)