import asyncio
from app.core.database import engine, Base, SessionLocal
from app.seeders import seed_commands, seed_default_project


async def init_db():
    print("🔄 Membangun ulang struktur tabel database SQLite...")
    async with engine.begin() as conn:
        # Menghapus tabel lama & membuat struktur tabel baru
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tabel database baru berhasil dibangun!")

    print("\n🌱 Menjalankan Seeder Data Master...")
    async with SessionLocal() as db:
        await seed_default_project(db)
        added_cmds = await seed_commands(db)
        print(f"✅ Seeder selesai! ({added_cmds} perintah master ditambahkan).")


if __name__ == "__main__":
    asyncio.run(init_db())