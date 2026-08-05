# Product Requirement Document (PRD)

## 1. Executive Summary & Product Overview
**QA Automata** adalah platform *web-based automated testing* & *visual regression tool* berbasis **FastAPI**, **Playwright**, dan **HTMX**. Platform ini dirancang untuk memudahkan QA Engineer, Developer, dan Project Manager dalam menyusun, mengeksekusi, dan merekam pengujian UI web tanpa perlu menulis skrip pengujian manual berulang.

Pembaruan versi ini berfokus pada **Manajemen Proyek**, **Keterlacakan Change Request (CR)**, serta **Otomatisasi Pembuatan Laporan Unit Test (UT Document Matrix)** dalam format Excel (`.xlsx`) standar industri (NSSOL / Enterprise Standard) dengan metode *Hybrid Fallback*.

---

## 2. Dynamic Hybrid Fallback Logic (UT Matrix Document Export)

Setiap pengujian dikaitkan dengan 9 kolom standar *UT Document Header*. Sistem menerapkan prinsip **Hybrid (Manual Override + Auto-Generated Fallback)**: jika pengguna tidak mengisi field opsional, sistem akan menghasilkan konten secara otomatis saat proses ekspor Excel.

| Header UT | Tipe Field DB | Logika Data di Excel (Fallback Rule) |
| :--- | :--- | :--- |
| **Case ID** | Auto Index | Urutan angka numerik sederhana: `1`, `2`, `3`, ... berdasarkan *loop index* saat pengujian diekspor. |
| **Theme** | `ut_theme` *(Opsional)* | 1. Teks manual `ut_theme`<br>2. *Fallback:* Nama Proyek (`Project.name`) |
| **Function name** | `ut_function_name` *(Opsional)* | 1. Teks manual `ut_function_name`<br>2. *Fallback:* Nama Skenario (`TestCase.name`) |
| **Action** | `ut_action` *(Opsional)* | 1. Teks manual `ut_action`<br>2. *Fallback:* Deskripsi/aksi dari langkah pertama (`TestStep` order #1) |
| **Condition 1** | `ut_condition_1` *(Opsional)* | 1. Teks manual `ut_condition_1`<br>2. *Fallback:* `TestCase.base_url` |
| **Condition 2** | `ut_condition_2` *(Opsional)* | 1. Teks manual `ut_condition_2`<br>2. *Fallback:* `"-"` |
| **Case classification** | `ut_classification` *(Opsional)* | 1. Teks manual `ut_classification`<br>2. *Fallback:* `"Normal"` |
| **How to test** | `ut_how_to_test` *(Opsional)* | 1. Teks manual `ut_how_to_test`<br>2. *Fallback:* Kompilasi otomatis dari seluruh daftar `TestStep` (e.g., `1. GOTO_URL /login\n2. TYPE_TEXT admin`) |
| **Expected results** | `ut_expected_results` *(Opsional)* | 1. Teks manual `ut_expected_results`<br>2. *Fallback:* Kompilasi otomatis dari langkah bermuatan `VERIFY_*` |

---

## 3. Database Entity Schema Architecture

### 3.1. Entity Relationship Diagram (Conceptual)
* **`Project`** `1` ──── `N` **`TestCase`** *(On Delete: CASCADE)*
* **`TestCase`** `1` ──── `N` **`TestStep`** *(On Delete: CASCADE)*
* **`TestCase`** `1` ──── `N` **`TestRun`** *(On Delete: CASCADE)*
* **`CommandDefinition`** *(Master Registry Data Perintah Playwright)*

### 3.2. Data Dictionary

#### A. Master `projects` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Proyek |
| `name` | String(100) | Not Null, Unique | Nama Proyek (e.g., *HRIS Portal*) |
| `description` | Text | Nullable | Deskripsi cakupan proyek |
| `created_at` | DateTime | Default UTC | Waktu pembuatan |

#### B. `test_cases` Table (Updated)
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Skenario |
| `project_id` | Integer | FK (`projects.id`), OnDelete CASCADE | ID Proyek Induk |
| `name` | String(100) | Not Null | Nama Skenario Pengujian |
| `base_url` | String(255) | Not Null | Target URL Utama |
| `test_type` | String(30) | Default: `REGRESSION` | `CHANGE_REQUEST`, `REGRESSION`, `NEW_FEATURE`, `HOTFIX` |
| `reference_number`| String(50) | Nullable | Nomor Identifikasi CR/Jira (e.g., *CR-2026-004*) |
| **UT Document Optional Fields** | | | |
| `ut_theme` | String(100) | Nullable | Manual Theme |
| `ut_function_name`| String(100) | Nullable | Manual Function Name |
| `ut_action` | Text | Nullable | Manual Action Description |
| `ut_condition_1` | Text | Nullable | Manual Condition 1 |
| `ut_condition_2` | Text | Nullable | Manual Condition 2 |
| `ut_classification`| String(50) | Nullable | Manual Classification (`Normal`, `Abnormal`, `Boundary`) |
| `ut_how_to_test` | Text | Nullable | Manual Steps Description |
| `ut_expected_results`| Text | Nullable | Manual Expected Results |
| `created_at` | DateTime | Default UTC | Waktu Pembuatan |

#### C. `test_steps` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Langkah |
| `test_case_id` | Integer | FK (`test_cases.id`), OnDelete CASCADE | ID Skenario Induk |
| `step_order` | Integer | Not Null | Urutan Langkah (1, 2, 3...) |
| `command` | String(50) | Not Null | Kode Perintah Playwright (e.g., `CLICK`, `TYPE_TEXT`) |
| `target_selector` | String(255) | Nullable | CSS/ID Selector |
| `input_value` | Text | Nullable | Nilai Input / Parameter |

#### D. `test_runs` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | String(50) | PK | UUID Run ID (e.g., `RUN-A5AE6B82`) |
| `test_case_id` | Integer | FK (`test_cases.id`), OnDelete CASCADE | ID Skenario |
| `status` | String(20) | Default: `PENDING` | `PENDING`, `RUNNING`, `SUCCESS`, `FAILED` |
| `video_url` | String(255) | Nullable | Relative Path Rekaman MP4 |
| `error_log` | Text | Nullable | Detail Error Traceback jika Failed |
| `executed_at` | DateTime | Default UTC | Waktu Eksekusi |

---

## 4. System Functional Requirements

### FR-1: Management Proyek & Seeder Default
* Sistem secara otomatis menjalankan *seeder* saat inisialisasi (`init_db.py`) untuk menjamin minimal ada 1 proyek bawaan: **"Default Project"**.
* Pengguna dapat membuat proyek baru via modal/form UI.
* Jika proyek dihapus, seluruh skenario (`test_cases`) di bawahnya akan terhapus otomatis (*Cascade Delete*).

### FR-2: Pengelompokan & Filter Skenario Berdasarkan Proyek & CR
* Pengguna dapat memfilter tampilan daftar skenario di Dashboard berdasarkan **Proyek** atau **Tipe Pengujian (Change Request)**.
* Nomor Referensi CR bersifat **opsional** untuk seluruh tipe pengujian.
* Setiap kartu skenario di UI akan menampilkan badge visual penanda status CR/Tipe pengujian (misal: Badge Biru `CR-2026-004`).

### FR-3: Editor Langkah Skenario Inline (HTMX)
* Dukungan penambahan, pembaruan (*inline edit* tanpa reload), dan penghapusan langkah pengujian (`TestStep`) secara interaktif.
* Urutan langkah (`step_order`) disesuaikan secara otomatis jika ada langkah yang dihapus di tengah urutan.

### FR-4: Eksekusi Async Cross-Platform & Streaming Bukti Pengujian
* Eksekusi browser Playwright berjalan di latar belakang (*background task*).
* Untuk OS Windows, eksekusi diisolasi di dalam `ThreadPoolExecutor` dengan `WindowsProactorEventLoopPolicy` guna mencegah `NotImplementedError`.
* Hasil pengujian merekam video web browser yang dikonversi ke format `.mp4` menggunakan FFmpeg dan ditayangkan melalui HTTP 206 Partial Content Streaming.
* Tangkapan layar (*full-page screenshot*) dari perintah `TAKE_SCREENSHOT_FULL` disimpan di `static/screenshots/`.

### FR-5: Modul Ekspor Laporan UT Document Matrix (`.xlsx`)
* Menyediakan endpoint ekspor yang menghasilkan berkas Excel `.xlsx` menggunakan `openpyxl`.
* Menerapkan logika *Hybrid Fallback* untuk mengisi 9 kolom header UT Document.
* Menyediakan baris tambahan berisi hasil aktual (`PASS`/`FAIL`) serta tautan bukti (*evidence*) video/screenshot dari hasil eksekusi terakhir.

---

## 5. Directory & Package Architecture (FastAPI Best Practices)

```text
qa_webapp/
├── app/
│   ├── api/
│   │   ├── deps.py                 # Dependency Injection (get_db)
│   │   └── v1/
│   │       ├── dashboard.py        # Router Dashboard, Project & Skenario HTMX
│   │       ├── export.py           # Router Ekspor Laporan UT Matrix Excel
│   │       └── media.py            # Router Streaming Video HTTP 206
│   ├── core/
│   │   ├── config.py               # Pydantic BaseSettings
│   │   └── database.py             # SQLAlchemy Async Engine & Session
│   ├── engine/
│   │   ├── executor.py             # Playwright Executor & Thread Pool Isolation
│   │   └── handlers.py             # Playwright Command Registries
│   ├── models/
│   │   └── models.py               # SQLAlchemy ORM Models (Project, TestCase, dll.)
│   ├── schemas/
│   │   └── schemas.py              # Pydantic Schemas (DTO)
│   ├── services/
│   │   └── export_service.py       # Logika Penyusunan Document UT & OpenPyXL Generator
│   ├── seeders.py                  # Seeder Master Command & Default Project
│   └── main.py                     # Minimalist Entrypoint
├── static/
│   ├── videos/                     # Output Rekaman Video (.mp4)
│   └── screenshots/                # Output Screenshots (.png)
├── templates/
│   ├── index.html                  # Main Layout & Project Filter
│   └── partials/
│       ├── project_modal.html      # Modal Buat Proyek Baru
│       ├── right_panel.html        # Detail Skenario & Form Metadata UT (Collapsible)
│       ├── step_list.html          # Tabel Steps dengan Action Edit & Delete
│       ├── step_edit_form.html     # Inline Edit Form Step
│       └── status.html             # Video Player & Execution Status
├── init_db.py                      # Database Initialization & Seeding Runner
├── .gitignore
├── requirements.txt
└── prd.md                          # Product Requirement Document
```

### FR-6: Reusable Scenario Architecture (INCLUDE_SCENARIO Command)
* Pengguna dapat menyisipkan skenario tes lain ke dalam skenario aktif menggunakan perintah master `INCLUDE_SCENARIO`.
* Nilai `input_value` menyimpan ID Skenario Target yang ingin dieksekusi.
* Mesin eksekusi Playwright mengeksekusi langkah-langkah sub-skenario secara rekursif dalam browser session context yang sama.
* Dilengkapi dengan **Circular Dependency Safeguard** untuk mendeteksi dan menghentikan loop panggilan antar-skenario tak terbatas secara otomatis.
* Ekspor Excel Laporan UT Document Matrix secara otomatis merakit ulang sub-langkah dari skenario yang disisipkan.