from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base

# jalankan 'python init_db.py' untuk generate database baru
# menggunakan SQLite
# menggunakan aiosqlite (Karena menggunakan FastAPI dan Playwright (yang bersifat async)) agar database tidak memblokir antrean server.
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./qa_database.db"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False} # Wajib untuk SQLite
)

# Membuat session database
SessionLocal = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine, 
    class_=AsyncSession,
    expire_on_commit=False
)

# Kelas dasar untuk model tabel kita nanti
Base = declarative_base()

# agar koneksi database otomatis terbuka dan tertutup setiap ada request HTTP
async def get_db():
    async with SessionLocal() as session:
        yield session