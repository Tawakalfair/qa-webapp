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

    class Config:
        env_file = ".env"

settings = Settings()

# Pastikan folder penyimpanan media terbuat
os.makedirs(settings.VIDEO_DIR, exist_ok=True)
os.makedirs(settings.SCREENSHOT_DIR, exist_ok=True)