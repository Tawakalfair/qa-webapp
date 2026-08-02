import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CommandDefinition

# Set up logger sederhana
logger = logging.getLogger("db_seeder")

# Katalog Master Data Perintah Playwright
INITIAL_COMMANDS = [
    {
        "code": "GOTO_URL",
        "label": "Membuka URL Target",
        "description": "Membuka URL utama atau relative path (misal: /login)",
        "requires_selector": False,
        "requires_value": True,
        "placeholder_selector": "-",
        "placeholder_value": "/login atau https://example.com"
    },
    {
        "code": "CLICK",
        "label": "Klik Elemen Target",
        "description": "Mengklik tombol, tautan, atau elemen HTML",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": "#btn-submit atau text='Masuk'",
        "placeholder_value": "-"
    },
    {
        "code": "DOUBLE_CLICK",
        "label": "Klik Dua Kali (Double Click)",
        "description": "Melakukan klik ganda pada elemen target",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": ".card-item",
        "placeholder_value": "-"
    },
    {
        "code": "RIGHT_CLICK",
        "label": "Klik Kanan Mouse",
        "description": "Melakukan klik kanan pada elemen target",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": "#context-target",
        "placeholder_value": "-"
    },
    {
        "code": "TYPE_TEXT",
        "label": "Ketik Teks Input",
        "description": "Mengisi kolom input/form dengan teks",
        "requires_selector": True,
        "requires_value": True,
        "placeholder_selector": "input[name='username']",
        "placeholder_value": "admin123"
    },
    {
        "code": "CLEAR_TEXT",
        "label": "Kosongkan Kolom Input",
        "description": "Menghapus/mengosongkan teks dari kolom input",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": "#search-input",
        "placeholder_value": "-"
    },
    {
        "code": "PRESS_KEY",
        "label": "Tekan Tombol Keyboard",
        "description": "Menekan tombol khusus keyboard (Enter, Tab, Escape)",
        "requires_selector": True,
        "requires_value": True,
        "placeholder_selector": "#search-input",
        "placeholder_value": "Enter"
    },
    {
        "code": "SELECT_OPTION",
        "label": "Pilih Dropdown (<select>)",
        "description": "Pilih opsi berdasarkan label pada elemen <select>",
        "requires_selector": True,
        "requires_value": True,
        "placeholder_selector": "#select-country",
        "placeholder_value": "Indonesia"
    },
    {
        "code": "CHECK",
        "label": "Centang Checkbox/Radio",
        "description": "Mencentang pilihan pada elemen checkbox atau radio button",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": "#agree-terms",
        "placeholder_value": "-"
    },
    {
        "code": "UNCHECK",
        "label": "Hapus Centang Checkbox",
        "description": "Hapus centang pada elemen checkbox",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": "#subscribe-newsletter",
        "placeholder_value": "-"
    },
    {
        "code": "HOVER",
        "label": "Arahkan Mouse (Hover)",
        "description": "Mengarahkan kursor mouse di atas elemen target",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": ".dropdown-toggle",
        "placeholder_value": "-"
    },
    {
        "code": "SCROLL_DOWN",
        "label": "Gulir Layar/Kontainer ke Bawah",
        "description": "Menggulir posisi layar atau elemen kontainer ke bawah (piksel)",
        "requires_selector": False,
        "requires_value": True,
        "placeholder_selector": ".scroll-container (opsional)",
        "placeholder_value": "300"
    },
    {
        "code": "SCROLL_UP",
        "label": "Gulir Layar/Kontainer ke Atas",
        "description": "Menggulir posisi layar atau elemen kontainer ke atas (piksel)",
        "requires_selector": False,
        "requires_value": True,
        "placeholder_selector": ".scroll-container (opsional)",
        "placeholder_value": "300"
    },
    {
        "code": "SCROLL_RIGHT",
        "label": "Gulir Layar/Kontainer ke Kanan",
        "description": "Menggulir posisi layar atau elemen kontainer ke kanan (piksel)",
        "requires_selector": False,
        "requires_value": True,
        "placeholder_selector": ".dt-scroll-body (opsional)",
        "placeholder_value": "300"
    },
    {
        "code": "TAKE_SCREENSHOT_FULL",
        "label": "Tangkap Layar Penuh (Full Page Screenshot)",
        "description": "Mengambil gambar screenshot seluruh halaman web dari atas sampai bawah",
        "requires_selector": False,
        "requires_value": False,
        "placeholder_selector": "-",
        "placeholder_value": "nama_custom.png (opsional)"
    },
    {
        "code": "WAIT",
        "label": "Tunggu Jeda (Detik)",
        "description": "Menunda eksekusi selama beberapa detik",
        "requires_selector": False,
        "requires_value": True,
        "placeholder_selector": "-",
        "placeholder_value": "3"
    },
    {
        "code": "WAIT_FOR_SELECTOR",
        "label": "Tunggu Elemen Muncul",
        "description": "Menunggu sampai elemen HTML muncul di layar",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": ".loading-spinner",
        "placeholder_value": "-"
    },
    {
        "code": "VERIFY_TEXT",
        "label": "Verifikasi Teks Elemen",
        "description": "Memastikan elemen mengandung teks yang diharapkan",
        "requires_selector": True,
        "requires_value": True,
        "placeholder_selector": ".alert-success",
        "placeholder_value": "Berhasil Login"
    },
    {
        "code": "VERIFY_ELEMENT_VISIBLE",
        "label": "Verifikasi Elemen Tampak",
        "description": "Memastikan elemen HTML tampak (visible) di layar",
        "requires_selector": True,
        "requires_value": False,
        "placeholder_selector": "#dashboard-widget",
        "placeholder_value": "-"
    }
]

async def seed_commands(db: AsyncSession) -> int:
    """
    Fungsi seeder mandiri untuk menyuntikkan daftar perintah awal ke database.
    Mencegah duplikasi dengan memeriksa keberadaan 'code' di tabel command_definitions.
    """
    added_count = 0
    for cmd_data in INITIAL_COMMANDS:
        result = await db.execute(
            select(CommandDefinition).where(CommandDefinition.code == cmd_data["code"])
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            new_cmd = CommandDefinition(**cmd_data)
            db.add(new_cmd)
            added_count += 1
            print(f"  ➕ [Seeder] Menambahkan perintah baru: {cmd_data['code']}")

    if added_count > 0:
        await db.commit()
        print(f"✅ [Seeder] Berhasil menambahkan {added_count} perintah ke database.")
    else:
        print("ℹ️ [Seeder] Seluruh katalog perintah master sudah ada di database.")

    return added_count