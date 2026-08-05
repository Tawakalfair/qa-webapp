from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import CommandDefinition, Project

INITIAL_COMMANDS = [
    {
        "code": "INCLUDE_SCENARIO", "label": "Menyisipkan Sub-Skenario",
        "description": "Menjalankan seluruh langkah dari skenario tes lain sebagai sub-langkah",
        "requires_selector": False, "requires_value": True,
        "placeholder_selector": "-", "placeholder_value": "ID Skenario Target (misal: 1)"
    },
    {
        "code": "GOTO_URL", "label": "Membuka URL Target",
        "description": "Membuka URL utama atau relative path",
        "requires_selector": False, "requires_value": True,
        "placeholder_selector": "-", "placeholder_value": "/login atau https://example.com"
    },
    {
        "code": "CLICK", "label": "Klik Elemen Target",
        "description": "Mengklik tombol atau elemen HTML",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": "#btn-submit", "placeholder_value": "-"
    },
    {
        "code": "DOUBLE_CLICK", "label": "Klik Dua Kali",
        "description": "Melakukan klik ganda pada elemen target",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": ".card-item", "placeholder_value": "-"
    },
    {
        "code": "RIGHT_CLICK", "label": "Klik Kanan Mouse",
        "description": "Melakukan klik kanan pada elemen target",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": "#context-target", "placeholder_value": "-"
    },
    {
        "code": "TYPE_TEXT", "label": "Ketik Teks Input",
        "description": "Mengisi kolom input dengan teks",
        "requires_selector": True, "requires_value": True,
        "placeholder_selector": "input[name='username']", "placeholder_value": "admin123"
    },
    {
        "code": "CLEAR_TEXT", "label": "Kosongkan Kolom Input",
        "description": "Mengosongkan teks pada kolom input",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": "#search-input", "placeholder_value": "-"
    },
    {
        "code": "PRESS_KEY", "label": "Tekan Tombol Keyboard",
        "description": "Menekan tombol keyboard (Enter, Tab, Escape)",
        "requires_selector": True, "requires_value": True,
        "placeholder_selector": "#search-input", "placeholder_value": "Enter"
    },
    {
        "code": "SELECT_OPTION", "label": "Pilih Dropdown (<select>)",
        "description": "Pilih opsi berdasarkan label pada elemen <select>",
        "requires_selector": True, "requires_value": True,
        "placeholder_selector": "#select-country", "placeholder_value": "Indonesia"
    },
    {
        "code": "CHECK", "label": "Centang Checkbox/Radio",
        "description": "Mencentang elemen checkbox atau radio",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": "#agree-terms", "placeholder_value": "-"
    },
    {
        "code": "UNCHECK", "label": "Hapus Centang Checkbox",
        "description": "Menghapus centang pada elemen checkbox",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": "#subscribe-newsletter", "placeholder_value": "-"
    },
    {
        "code": "HOVER", "label": "Arahkan Mouse (Hover)",
        "description": "Mengarahkan kursor mouse di atas elemen",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": ".dropdown-toggle", "placeholder_value": "-"
    },
    {
        "code": "SCROLL_DOWN", "label": "Gulir Layar/Kontainer ke Bawah",
        "description": "Menggulir posisi layar ke bawah (piksel)",
        "requires_selector": False, "requires_value": True,
        "placeholder_selector": ".scroll-container (opsional)", "placeholder_value": "300"
    },
    {
        "code": "SCROLL_UP", "label": "Gulir Layar/Kontainer ke Atas",
        "description": "Menggulir posisi layar ke atas (piksel)",
        "requires_selector": False, "requires_value": True,
        "placeholder_selector": ".scroll-container (opsional)", "placeholder_value": "300"
    },
    {
        "code": "SCROLL_RIGHT", "label": "Gulir Layar/Kontainer ke Kanan",
        "description": "Menggulir posisi layar ke kanan (piksel)",
        "requires_selector": False, "requires_value": True,
        "placeholder_selector": ".dt-scroll-body (opsional)", "placeholder_value": "300"
    },
    {
        "code": "TAKE_SCREENSHOT_FULL", "label": "Tangkap Layar Penuh",
        "description": "Mengambil screenshot halaman penuh (full page)",
        "requires_selector": False, "requires_value": False,
        "placeholder_selector": "-", "placeholder_value": "custom_name.png (opsional)"
    },
    {
        "code": "WAIT", "label": "Tunggu Jeda (Detik)",
        "description": "Menunda eksekusi selama beberapa detik",
        "requires_selector": False, "requires_value": True,
        "placeholder_selector": "-", "placeholder_value": "3"
    },
    {
        "code": "WAIT_FOR_SELECTOR", "label": "Tunggu Elemen Muncul",
        "description": "Menunggu sampai elemen HTML muncul",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": ".loading-spinner", "placeholder_value": "-"
    },
    {
        "code": "VERIFY_TEXT", "label": "Verifikasi Teks Elemen",
        "description": "Memastikan elemen mengandung teks yang diharapkan",
        "requires_selector": True, "requires_value": True,
        "placeholder_selector": ".alert-success", "placeholder_value": "Berhasil Login"
    },
    {
        "code": "VERIFY_ELEMENT_VISIBLE", "label": "Verifikasi Elemen Tampak",
        "description": "Memastikan elemen HTML tampak di layar",
        "requires_selector": True, "requires_value": False,
        "placeholder_selector": "#dashboard-widget", "placeholder_value": "-"
    }
]


async def seed_default_project(db: AsyncSession) -> Project:
    """Menjamin tersedianya proyek bawaan (Default Project) di database."""
    result = await db.execute(select(Project).where(Project.name == "Default Project"))
    project = result.scalar_one_or_none()
    
    if not project:
        project = Project(
            name="Default Project",
            description="Proyek bawaan sistem untuk skenario yang tidak dikaitkan dengan proyek spesifik."
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        print("✅ Default Project berhasil dibuat.")
    else:
        print("ℹ️ Default Project sudah tersedia.")
        
    return project


async def seed_commands(db: AsyncSession) -> int:
    """Menyimpan master data perintah Playwright ke database."""
    added_count = 0
    for cmd_data in INITIAL_COMMANDS:
        result = await db.execute(
            select(CommandDefinition).where(CommandDefinition.code == cmd_data["code"])
        )
        if not result.scalar_one_or_none():
            db.add(CommandDefinition(**cmd_data))
            added_count += 1
            
    if added_count > 0:
        await db.commit()
    return added_count