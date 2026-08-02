📝 QA Automata - Project Cheat Sheet & Development Notes

Dokumen ini berisi rangkuman perintah penting, struktur proyek, dan catatan teknis untuk platform otomatisasi web QA Automata (FastAPI + HTMX + Playwright + SQLite).

🚀 Quick Start (Perintah Memulai Kerja Harian)

Setiap kali baru membuka komputer/terminal, jalankan urutan berikut:

# 1. Masuk ke direktori proyek
cd /path/ke/qa_webapp

# 2. Aktifkan Virtual Environment Python 3.12 (Linux/macOS)
uv venv
source .venv/bin/activate
pip install requirements.txt / uv pip install requirements.txt
playwright install chromium
python init_db.py

# 3. Pastikan FFmpeg terinstal di sistem OS
# Ubuntu/Debian: sudo apt install -y ffmpeg

# 4. Jalankan Web Server FastAPI (dengan Auto-Reload)
uvicorn app.main:app --reload


Akses Aplikasi:

Dashboard Utama: http://127.0.0.1:8000

Dokumentasi API Interactive (Swagger UI): http://127.0.0.1:8000/docs

🛠️ Manajemen Perintah & Dependensi

1. Virtual Environment (.venv)

Cek status venv aktif:

Perhatikan indikator (.venv) di sebelah kiri prompt terminal.

Atau ketik: which python (harus menunjuk ke folder .venv/bin/python).

Nonaktifkan venv: deactivate

2. Pengelolaan Library (pip)

Instal library baru:

pip install <nama_library>


Kunci/Perbarui file dependensi:

pip freeze > requirements.txt


Instal ulang semua library dari requirements.txt:

pip install -r requirements.txt


3. Database (SQLite + Async SQLAlchemy)

Inisialisasi / Reset Tabel Database:

python init_db.py


Membaca app/models.py dan menghasilkan file database qa_database.db.

4. Engine Browser (Playwright)

Instalasi Browser & Dependency Perekam Video (FFmpeg):

playwright install chromium


📂 Struktur Berkas Proyek

qa_webapp/
├── .venv/                      # Virtual environment Python 3.12
├── app/
│   ├── database.py             # Koneksi SQLite + Async SQLAlchemy (expire_on_commit=False)
│   ├── models.py               # Model Tabel (TestCase, TestStep, TestRun)
│   ├── engine.py               # Mesin Perekam & Eksekusi Playwright (GOTO_URL, CLICK, TYPE, dll)
│   └── main.py                 # REST API & Rute HTMX Partial Rendering
├── static/
│   └── videos/                 # Tempat penyimpanan rekaman hasil pengujian (.webm/.mp4)
├── templates/
│   ├── index.html              # Halaman Dashboard Utama
│   └── partials/               # Serpihan Komponen HTML (HTMX Partials)
│       ├── right_panel.html    # Panel Detail Skenario & Form Step
│       ├── step_list.html      # Daftar Urutan Langkah Pengujian
│       └── status.html         # Indikator Polling Real-time & Pemutar Video
├── init_db.py                  # Script Pembuat Tabel SQLite
├── qa_database.db              # Database File SQLite
├── requirements.txt            # Daftar Dependensi Python
└── notepad.md                  # Dokumentasi Catatan Proyek


💡 Catatan Teknis & Solusi Masalah Krusial

1. Penggabungan Relative URL Cerdas (app/engine.py)

Agar pengguna dapat mengetik path relatif (seperti /user/profile) pada perintah GOTO_URL tanpa harus mengetik ulang domain lengkap, kita menggunakan urllib.parse.urljoin:

import urllib.parse

if not step.input_value:
    url = test_case.base_url
elif step.input_value.startswith(("http://", "https://")):
    url = step.input_value
else:
    url = urllib.parse.urljoin(test_case.base_url, step.input_value)


2. Mencegah Error MissingGreenlet SQLAlchemy (app/database.py)

Saat merender partial HTML Jinja2/HTMX secara asinkron setelah proses db.commit(), SQLAlchemy perlu dicegah agar tidak menghapus (expire) data di memori Python:

SessionLocal = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine, 
    class_=AsyncSession,
    expire_on_commit=False  # <-- Kunci pencegah MissingGreenlet Error
)


3. Pemahaman Atribut Utama HTMX

Aplikasi kita menggunakan HTMX untuk menghindari kerumitan JavaScript Vanilla:

hx-get="/testcase/1": Memanggil server via HTTP GET untuk mengambil fragmen HTML.

hx-post="/testcase/1/run": Mengirim data via HTTP POST secara asinkron tanpa reload.

hx-delete="/testcase/1/step/5": Mengirim HTTP DELETE untuk menghapus langkah.

hx-target="#steps-list-container": Menentukan elemen div mana di layar yang akan digantikan isinya oleh respon HTML server.

hx-confirm="Yakin?": Menampilkan pop-up konfirmasi browser sebelum menembak server.

hx-trigger="every 1.5s": Melakukan polling status eksekusi otomatis ke server setiap 1,5 detik hingga status selesai.

📋 Jenis Perintah Pengujian yang Didukung (TestStep)

GOTO_URL: Membuka URL (Base URL atau relative path /path).

CLICK: Mengklik elemen web berdasarkan CSS selector / text="Nama".

TYPE_TEXT: Mengisi kolom formulir teks.

WAIT: Menunda eksekusi beberapa detik (misal: 3).

VERIFY_TEXT: Memastikan teks tertentu hadir pada elemen target.