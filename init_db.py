import asyncio
from app.core.database import engine, Base, SessionLocal
from app.seeders import seed_commands

async def init_db():
    """
    Script utama untuk inisialisasi tabel database dan pemanggilan seeder modular.
    """
    print("🔄 Membangun struktur tabel database SQLite...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tabel database berhasil diperbarui/dibuat!")

    print("\n🌱 Menjalankan Seeder Data Master...")
    async with SessionLocal() as db:
        await seed_commands(db)

    print("\n🎉 Proses inisialisasi database dan seeding selesai sempurna!")

if __name__ == "__main__":
    asyncio.run(init_db())