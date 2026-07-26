import asyncio
from app.database import engine, Base
# mengimpor file models agar SQLAlchemy membaca struktur tabelnya
from app import models 

async def init_models():
    """
    Fungsi ini bertugas membuat file qa_database.db 
    dan merancang tabel di dalamnya sesuai dengan definisi di models.py
    """
    async with engine.begin() as conn:
        print("Membangun struktur database SQLite...")
        # Perintah ini akan mengecek apakah tabel sudah ada, jika belum ia akan membuatnya.
        await conn.run_sync(Base.metadata.create_all)
        print("Tabel berhasil dibuat!")

if __name__ == "__main__":
    # Menjalankan fungsi asynchronous di atas
    asyncio.run(init_models())