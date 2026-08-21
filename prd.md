# Product Requirement Document (PRD)

## 1. Executive Summary & Product Overview
**QA Automata** adalah platform *web-based automated testing* & *visual regression tool* berbasis **FastAPI**, **Playwright**, dan **HTMX**[cite: 6]. Platform ini dirancang untuk memudahkan QA Engineer, Developer, dan Project Manager dalam menyusun, mengeksekusi, dan merekam pengujian UI web tanpa perlu menulis skrip pengujian manual berulang[cite: 6].

Pembaruan v3.0 ini berfokus pada **Penyegaran UI/UX Modular (Dual-View Architecture)**, **Halaman Inventory & Manajemen Aksi Massal (Bulk Operations)**, **Mesin Eksekusi Massal (Smart Batch Execution)** yang stabil di Windows/Linux, **Multi-User Data Privacy**, serta **Otomatisasi Laporan Unit Test (UT Document Matrix)** dalam format Excel (`.xlsx`) standar industri[cite: 6].

---

## 2. Dynamic Hybrid Fallback Logic (UT Matrix Document Export)

Setiap pengujian dikaitkan dengan 9 kolom standar *UT Document Header*[cite: 6]. Sistem menerapkan prinsip **Hybrid (Manual Override + Auto-Generated Fallback)**: jika pengguna tidak mengisi field opsional, sistem akan menghasilkan konten secara otomatis saat proses ekspor Excel[cite: 6].

| Header UT | Tipe Field DB | Logika Data di Excel (Fallback Rule) |
| :--- | :--- | :--- |
| **Case ID** | Auto Index | Urutan angka numerik sederhana: `1`, `2`, `3`, ... berdasarkan *loop index* saat pengujian diekspor[cite: 6]. |
| **Theme** | `ut_theme` *(Opsional)* | 1. Teks manual `ut_theme`<br>2. *Fallback:* Nama Proyek (`Project.name`)[cite: 6] |
| **Function name** | `ut_function_name` *(Opsional)* | 1. Teks manual `ut_function_name`<br>2. *Fallback:* Nama Skenario (`TestCase.name`)[cite: 6] |
| **Action** | `ut_action` *(Opsional)* | 1. Teks manual `ut_action`<br>2. *Fallback:* Deskripsi/aksi dari langkah pertama (`TestStep` order #1)[cite: 6] |
| **Condition 1** | `ut_condition_1` *(Opsional)* | 1. Teks manual `ut_condition_1`<br>2. *Fallback:* `TestCase.base_url`[cite: 6] |
| **Condition 2** | `ut_condition_2` *(Opsional)* | 1. Teks manual `ut_condition_2`<br>2. *Fallback:* `"-"`[cite: 6] |
| **Case classification** | `ut_classification` *(Opsional)* | 1. Teks manual `ut_classification`<br>2. *Fallback:* `"Normal"`[cite: 6] |
| **How to test** | `ut_how_to_test` *(Opsional)* | 1. Teks manual `ut_how_to_test`<br>2. *Fallback:* Kompilasi otomatis dari seluruh daftar `TestStep` (e.g., `1. GOTO_URL /login\n2. TYPE_TEXT admin`)[cite: 6] |
| **Expected results** | `ut_expected_results` *(Opsional)* | 1. Teks manual `ut_expected_results`<br>2. *Fallback:* Kompilasi otomatis dari langkah bermuatan `VERIFY_*` atau `ASSERT`[cite: 6] |

---

## 3. Database Entity Schema & Migration Architecture

### 3.1. Entity Relationship Diagram (Conceptual)
* **`User`** `1` ──── `N` **`Project`** *(On Delete: CASCADE)*[cite: 6]
* **`Project`** `1` ──── `N` **`TestCase`** *(On Delete: CASCADE)*[cite: 6]
* **`TestCase`** `1` ──── `N` **`TestStep`** *(On Delete: CASCADE)*[cite: 6]
* **`TestCase`** `1` ──── `N` **`TestRun`** *(On Delete: CASCADE)*[cite: 6]
* **`CommandDefinition`** *(Master Registry Data Perintah Playwright - Global)*[cite: 6]

### 3.2. Data Dictionary

#### A. Master `users` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Pengguna[cite: 6] |
| `username` | String(50) | Not Null, Unique, Index | Nama pengguna untuk Login[cite: 6] |
| `hashed_password` | String(255) | Not Null | Kata sandi terenkripsi (`bcrypt` murni)[cite: 6] |
| `created_at` | DateTime | Default UTC | Waktu pembuatan akun[cite: 6] |

#### B. Master `projects` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Proyek[cite: 6] |
| `user_id` | Integer | FK (`users.id`), OnDelete CASCADE | Pemilik Proyek (Isolasi Data)[cite: 6] |
| `name` | String(100) | Not Null | Nama Proyek (e.g., *HRIS Portal*)[cite: 6] |
| `description` | Text | Nullable | Deskripsi cakupan proyek[cite: 6] |
| `created_at` | DateTime | Default UTC | Waktu pembuatan[cite: 6] |

#### C. `test_cases` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Skenario[cite: 6] |
| `project_id` | Integer | FK (`projects.id`), OnDelete CASCADE | ID Proyek Induk[cite: 6] |
| `name` | String(100) | Not Null | Nama Skenario Pengujian[cite: 6] |
| `base_url` | String(255) | Not Null | Target URL Utama[cite: 6] |
| `test_type` | String(30) | Default: `REGRESSION` | `CHANGE_REQUEST`, `REGRESSION`, `NEW_FEATURE`, `HOTFIX`[cite: 6] |
| `reference_number`| String(50) | Nullable | Nomor Identifikasi CR/Jira (e.g., *CR-2026-004*)[cite: 6] |
| `ut_theme` | String(100) | Nullable | Manual Theme[cite: 6] |
| `ut_function_name`| String(100) | Nullable | Manual Function Name[cite: 6] |
| `ut_action` | Text | Nullable | Manual Action Description[cite: 6] |
| `ut_condition_1` | Text | Nullable | Manual Condition 1[cite: 6] |
| `ut_condition_2` | Text | Nullable | Manual Condition 2[cite: 6] |
| `ut_classification`| String(50) | Nullable | Manual Classification (`Normal`, `Abnormal`, `Boundary`)[cite: 6] |
| `ut_how_to_test` | Text | Nullable | Manual Steps Description[cite: 6] |
| `ut_expected_results`| Text | Nullable | Manual Expected Results[cite: 6] |
| `created_at` | DateTime | Default UTC | Waktu Pembuatan[cite: 6] |

#### D. `test_steps` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Langkah[cite: 6] |
| `test_case_id` | Integer | FK (`test_cases.id`), OnDelete CASCADE | ID Skenario Induk[cite: 6] |
| `step_order` | Integer | Not Null | Urutan Langkah (1, 2, 3...)[cite: 6] |
| `command` | String(50) | Not Null | Kode Perintah (e.g., `CLICK`, `ASSERT`)[cite: 6] |
| `target_selector` | String(255) | Nullable | CSS/ID Selector[cite: 6] |
| `input_value` | Text | Nullable | Nilai Input / Parameter[cite: 6] |

#### E. `test_runs` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | String(50) | PK | UUID Run ID (e.g., `RUN-A5AE6B82`)[cite: 6] |
| `test_case_id` | Integer | FK (`test_cases.id`), OnDelete CASCADE | ID Skenario[cite: 6] |
| `status` | String(20) | Default: `PENDING` | `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`[cite: 6] |
| `video_url` | String(255) | Nullable | Relative Path Rekaman MP4 (`temp_` untuk auto-cleanup)[cite: 6] |
| `error_log` | Text | Nullable | Detail Error Traceback jika Failed[cite: 6] |
| `executed_at` | DateTime | Default UTC | Waktu Eksekusi[cite: 6] |

---

## 4. System Functional Requirements

### FR-1: Otentikasi & Keamanan (Multi-User Data Privacy)
* Aplikasi dilindungi oleh sistem otentikasi login menggunakan **Pure `bcrypt`** dan **JWT (JSON Web Token)**[cite: 6].
* Sesi pengguna disimpan dengan aman menggunakan **HttpOnly Cookie** guna mencegah serangan XSS[cite: 6].
* Middleware dependencies (`get_current_user`) mengalihkan pengguna anonim ke halaman `/login`[cite: 6].

### FR-2: Isolasi Data Proyek & Skenario
* Seluruh operasi CRUD divalidasi mutlak menggunakan `current_user.id`[cite: 6].
* Mencegah *Broken Access Control* / IDOR sehingga pengguna tidak dapat memanipulasi data pengguna lain[cite: 6].

### FR-3: Dual-View UI Architecture (Workspace & Scenario Inventory)
* **Workspace (`/`)**: 
  * Panel kiri berisi *full-height scenario list* dengan *live search* HTMX dan tombol `+ New Scenario` modal.
  * Kartu skenario yang sedang dibuka mendapatkan efek *border/highlight* biru aktif yang berpindah secara instan saat diklik.
* **Scenario Inventory (`/scenarios`)**:
  * Antarmuka tabel *full-width* dengan filter proyek dan kolom pencarian nama skenario.
  * Menampilkan ID, nama skenario, nama proyek, tipe tes, jumlah langkah, dan indikator status pengujian terakhir (`PASS`, `FAIL`, `UNTESTED`).
  * Tombol **`⚡ Open`** untuk membuka skenario terpilih di Workspace Editor lengkap dengan sorot kartu aktif.

### FR-4: Manajemen Aksi Massal (Bulk Operations)
* **Multi-Select Checkbox**: Pengguna dapat mencentang skenario individual atau menggunakan *master select-all checkbox*.
* **Batch Duplicate Modal**:
  * Membuka modal pratinjau yang menampilkan seluruh skenario terpilih.
  * Menyediakan kolom input nama baru yang otomatis terisi prefix `Copy of [Scenario Name]` atau dapat disesuaikan secara manual.
  * Mendukung pemilihan proyek target baru.
  * Skenario hasil duplikat menyalin seluruh 8 atribut metadata UT Document + seluruh langkah `TestStep` dan secara otomatis diurutkan di paling atas (`ORDER BY id DESC`).
* **Batch Delete**: Menghapus seluruh skenario terpilih secara bersamaan dengan dialog konfirmasi HTMX.
* **Auto State Recalculation**: Menggunakan `hx-on::after-swap` untuk secara otomatis mereset hitungan badge `0 selected` dan menonaktifkan tombol aksi begitu tabel di-*swap*.

### FR-5: Tabbed Workspace Editor & Embedded Detail Modal
* **Tabbed Workspace (`right_panel.html`)**:
  * **Tab 1 (`⚡ Test Steps`)**: Form penambahan langkah instruksi, pencarian *sub-scenario*, dan tabel urutan langkah.
  * **Tab 2 (`📋 UT Metadata`)**: Formulir pengisian 8 atribut UT Document Matrix.
  * **Tab 3 (`📽️ Execution & Results`)**: Kontrol eksekusi pengujian (*Run Test*), checkbox rekaman video, status pengujian, traceback error, dan pemutar video MP4.
* **Scenario Detail Modal (`scenario_detail_modal.html`)**:
  * Dapat diakses dari tombol **`👁️ Detail`** pada halaman Scenario Inventory.
  * Memungkinkan pengeditan informasi utama, metadata UT, penyusunan langkah, serta penjalankan pengujian (*Run Test*) langsung dari dalam modal.
  * Pembaruan data di dalam modal secara otomatis merefleksikan perubahan ke tabel Inventory di belakangnya via HTMX Out-of-Band (OOB) Swap.

### FR-6: Editor Langkah Inline & Sub-Scenario Navigation
* Dukungan penambahan, pembaruan (*inline edit*), perubahan urutan (Naik `⬆️` / Turun `⬇️`), dan penghapusan langkah (`TestStep`).
* Penyesuaian otomatis urutan `step_order` jika ada langkah di tengah yang dihapus.
* Perintah `INCLUDE_SCENARIO` untuk menyisipkan skenario lain sebagai sub-langkah yang dilengkapi *Circular Dependency Safeguard*.

### FR-7: Mesin Eksekusi Massal & Compatibility Layer Windows
* **Smart Batch Execution**:
  * Menggunakan *Synchronous Worker Thread* yang terisolasi dengan `WindowsProactorEventLoopPolicy` (`ProactorEventLoop`) untuk mencegah `NotImplementedError` pada Playwright subprocess di Windows (Python 3.13+).
  * Eksekusi batch berjalan secara sekuensial (antrean 1 per 1) di latar belakang untuk menjaga pemakaian RAM dan CPU server tetap stabil.
* **Real-Time Batch Progress**:
  * Polling progres berkala (`/batch-progress`).
  * Ketika progres mencapai 100%, backend mengirimkan HTMX OOB Swap untuk memperbarui 3 kartu ringkasan (`Lulus`, `Gagal`, `Belum Dites`) secara *real-time* di modal ekspor.

### FR-8: Modul Ekspor Laporan UT Document Matrix (`.xlsx`)
* Menggenerasi laporan Excel berstandar NSSOL dengan lembar *Evidence Screenshot* berukuran presisi ($57 \times 32\text{ cm}$).
* Modal ringkasan status pengujian sebelum ekspor.
* Pembersihan berkas tangkapan layar sementara secara otomatis dari disk setelah pengunduhan selesai.

---

## 5. Directory Architecture & Package Structure

```text
qa_webapp/
├── app/
│   ├── api/
│   │   ├── deps.py                 # Dependency Injection (get_db, get_current_user)[cite: 6]
│   │   └── v1/
│   │       ├── auth.py             # Router Authentication & JWT Cookie Setter[cite: 6]
│   │       ├── dashboard.py        # Router Workspace, Project, TestCase & Steps CRUD[cite: 6]
│   │       ├── export.py           # Router Ekspor UT Matrix Excel & Progress Polling[cite: 6]
│   │       ├── media.py            # Router Streaming Video HTTP 206[cite: 6]
│   │       └── scenarios.py        # Router Scenario Inventory, Bulk Duplicate/Delete & Detail Modal
│   ├── core/
│   │   ├── config.py               # Pydantic Settings (DB URL, JWT Secret Key)[cite: 6]
│   │   ├── database.py             # SQLAlchemy Async Engine & Session[cite: 6]
│   │   └── security.py             # Pure bcrypt Password Hashing & JWT Core Engine[cite: 6]
│   ├── engine/
│   │   ├── executor.py             # Playwright Executor, Video Temp Handler & Proactor Policy[cite: 6]
│   │   └── handlers.py             # Playwright Command Registries & Smart Assert[cite: 6]
│   ├── models/
│   │   └── models.py               # SQLAlchemy ORM Models (User, Project, TestCase, dll.)[cite: 6]
│   ├── schemas/
│   │   └── schemas.py              # Pydantic Schemas (DTO)[cite: 6]
│   ├── services/
│   │   └── export_service.py       # Logika OpenPyXL Generator & Image Evidence Inserter[cite: 6]
│   ├── seeders.py                  # Seeder Admin User, Default Project & Command Dictionary[cite: 6]
│   └── main.py                     # Entrypoint & Exception Handler[cite: 6]
├── static/
│   ├── js/                         # Static JS (htmx.min.js, tailwindcss.js, app.js)
│   ├── videos/                     # Output Rekaman Video (.mp4) & Temp Files[cite: 6]
│   └── screenshots/                # Output Screenshots (.png)[cite: 6]
├── templates/
│   ├── login.html                  # Halaman UI Authentication Tailwind[cite: 6]
│   ├── index.html                  # Main Layout Workspace Editor
│   ├── scenarios.html              # Full-Width Scenario Inventory Management Page
│   └── partials/
│       ├── create_case_modal.html  # Modal Buat Skenario Baru
│       ├── bulk_copy_modal.html    # Modal Batch Duplicate dengan Preview Penamaan
│       ├── scenario_detail_modal.html # Modal Detail Skenario dengan Embedded Runner
│       ├── scenario_table.html     # Partial Tabel Inventory dengan Checkbox Selection
│       ├── case_list.html          # Partial List Sidebar Kiri dengan Sorot Kartu Aktif
│       ├── right_panel.html        # Workspace Editor 3 Tab Interaktif
│       ├── step_list.html          # Tabel Steps dengan Aksi Reorder (⬆️/⬇️), Edit, Delete
│       ├── step_edit_form.html     # Inline Edit Form Step
│       ├── export_modal.html       # Modal Ringkasan Status Ekspor & Batch Progress
│       └── status.html             # Video Player, Error Log, & Toolbar Aksi Video
├── migrate_db.py                  # Skrip Migrasi Data SQLite ke PostgreSQL
├── init_db.py                      # Database Initialization & Admin Seeding Runner[cite: 6]
├── requirements.txt                # Dependensi Aplikasi (FastAPI, Playwright, openpyxl, asyncpg, dll)
└── prd.md                          # Product Requirement Document

# 6. Deployment & Server Hardware Specifications
Komponen	            Spesifikasi Minimal (Demo / Single User)	Spesifikasi  Rekomendasi
CPU / Processor	        2 vCPU (Dual Core)	                        4 vCPU (Quad Core)
RAM (Memory)	        2 GB RAM	                                8 GB RAM
Penyimpanan (Storage)	20 GB SSD	                                50 GB NVMe / Fast SSD
Sistem Operasi (OS)	    Ubuntu Server 22.04 LTS / Windows 10	    Ubuntu Server 24.04 LTS / Debian 12
Database Engine	        SQLite (Bawaan)	                            PostgreSQL (asyncpg driver)