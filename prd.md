# Product Requirement Document (PRD)

## 1. Executive Summary & Product Overview
**QA Automata** adalah platform *web-based automated testing* & *visual regression tool* berbasis **FastAPI**, **Playwright**, dan **HTMX**. Platform ini dirancang untuk memudahkan QA Engineer, Developer, dan Project Manager dalam menyusun, mengeksekusi, dan merekam pengujian UI web tanpa perlu menulis skrip pengujian manual berulang.

Pembaruan versi ini berfokus pada **Multi-User Authentication & Data Privacy**, **Manajemen Proyek Terisolasi**, **Keterlacakan Change Request (CR)**, serta **Otomatisasi Pembuatan Laporan Unit Test (UT Document Matrix)** dalam format Excel (`.xlsx`) standar industri (NSSOL / Enterprise Standard) dengan metode *Hybrid Fallback*.

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
| **Expected results** | `ut_expected_results` *(Opsional)* | 1. Teks manual `ut_expected_results`<br>2. *Fallback:* Kompilasi otomatis dari langkah bermuatan `VERIFY_*` atau `ASSERT` |

---

## 3. Database Entity Schema Architecture

### 3.1. Entity Relationship Diagram (Conceptual)
* **`User`** `1` ──── `N` **`Project`** *(On Delete: CASCADE)*
* **`Project`** `1` ──── `N` **`TestCase`** *(On Delete: CASCADE)*
* **`TestCase`** `1` ──── `N` **`TestStep`** *(On Delete: CASCADE)*
* **`TestCase`** `1` ──── `N` **`TestRun`** *(On Delete: CASCADE)*
* **`CommandDefinition`** *(Master Registry Data Perintah Playwright - Global)*

### 3.2. Data Dictionary

#### A. Master `users` Table (New)
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Pengguna |
| `username` | String(50) | Not Null, Unique, Index | Nama pengguna untuk Login |
| `hashed_password` | String(255) | Not Null | Kata sandi terenkripsi (Pure `bcrypt`) |
| `created_at` | DateTime | Default UTC | Waktu pembuatan akun |

#### B. Master `projects` Table (Updated)
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Unik Proyek |
| `user_id` | Integer | FK (`users.id`), OnDelete CASCADE | Pemilik Proyek (Data Isolation) |
| `name` | String(100) | Not Null | Nama Proyek (e.g., *HRIS Portal*) |
| `description` | Text | Nullable | Deskripsi cakupan proyek |
| `created_at` | DateTime | Default UTC | Waktu pembuatan |
*Note: Kombinasi `user_id` dan `name` bersifat Unique (uix_user_project_name).*

#### C. `test_cases` Table
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

#### D. `test_steps` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto-increment | ID Langkah |
| `test_case_id` | Integer | FK (`test_cases.id`), OnDelete CASCADE | ID Skenario Induk |
| `step_order` | Integer | Not Null | Urutan Langkah (1, 2, 3...) |
| `command` | String(50) | Not Null | Kode Perintah (e.g., `CLICK`, `ASSERT`) |
| `target_selector` | String(255) | Nullable | CSS/ID Selector |
| `input_value` | Text | Nullable | Nilai Input / Parameter |

#### E. `test_runs` Table
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | String(50) | PK | UUID Run ID (e.g., `RUN-A5AE6B82`) |
| `test_case_id` | Integer | FK (`test_cases.id`), OnDelete CASCADE | ID Skenario |
| `status` | String(20) | Default: `PENDING` | `PENDING`, `RUNNING`, `SUCCESS`, `FAILED` |
| `video_url` | String(255) | Nullable | Relative Path Rekaman MP4 (`temp_` untuk auto-cleanup) |
| `error_log` | Text | Nullable | Detail Error Traceback jika Failed |
| `executed_at` | DateTime | Default UTC | Waktu Eksekusi |

---

## 4. System Functional Requirements

### FR-1: Otentikasi & Keamanan (Multi-User Data Privacy)
* Aplikasi dilindungi oleh sistem otentikasi login menggunakan **Pure `bcrypt`** (tanpa dependensi usang) dan token **JWT (JSON Web Token)**.
* Sesi pengguna disimpan dengan aman di sisi klien menggunakan **HttpOnly Cookie** guna mencegah serangan XSS.
* Middleware dependencies (`get_current_user`) memastikan pengguna anonim akan dialihkan (*redirect*) ke halaman `/login`.
* Seeder inisialisasi (`init_db.py`) secara otomatis menciptakan 1 akun super user (*admin / admin123*) dan 1 Proyek default yang terikat padanya.

### FR-2: Isolasi Data Manajemen Proyek & Skenario
* Seluruh operasi CRUD (Create, Read, Update, Delete) pada endpoint Dashboard, Proyek, dan Skenario di-*filter* mutlak berdasarkan `current_user.id`. 
* Pengguna tidak dapat melihat, memodifikasi, mengekspor, ataupun mengeksekusi Proyek dan Skenario milik pengguna lain meskipun memanipulasi URL parameter (mencegah *Broken Access Control* / IDOR).

### FR-3: Pengelompokan & Filter Skenario Berdasarkan Proyek & CR
* Pengguna dapat memfilter tampilan daftar skenario di Dashboard berdasarkan **Proyek** atau **Tipe Pengujian (Change Request)**.
* Nomor Referensi CR bersifat **opsional** untuk seluruh tipe pengujian.
* Setiap kartu skenario di UI akan menampilkan badge visual penanda status CR/Tipe pengujian yang ter-*update* secara *real-time* via HTMX Out-of-Band (OOB) swap.

### FR-4: Editor Langkah Skenario Inline (HTMX)
* Dukungan penambahan, pembaruan (*inline edit*), perubahan urutan (Naik/Turun), dan penghapusan langkah pengujian (`TestStep`) secara interaktif.
* Urutan langkah (`step_order`) disesuaikan secara otomatis jika ada langkah yang dihapus di tengah urutan.

### FR-5: Eksekusi Async Cross-Platform & Streaming Bukti Pengujian
* Eksekusi browser Playwright berjalan di latar belakang (*background task*).
* Eksekusi diisolasi di dalam `Async Engine` lokal untuk mencegah *Deadlock* pada antrean Uvicorn, dan mengimplementasikan *fallback handler* yang menjamin penutupan *browser context* jika terjadi *Exception* atau *Timeout* (Batas Eksekusi 60 Detik / Timeout ASSERT 5 Detik).
* Menghasilkan rekaman MP4 sementara (`temp_`) yang bisa di-*preview*, disimpan secara permanen, atau dihapus manual/otomatis (*Auto-cleanup*).
* Tangkapan layar (*full-page screenshot*) disimpan terstruktur dengan format `case_{case_id}_step_{step_order}.png` agar aman dari penumpukan data.

### FR-6: Modul Ekspor Laporan UT Document Matrix (`.xlsx`)
* Endpoint ekspor `/export/ut-matrix` menghasilkan dokumen Excel yang dilengkapi *Evidence Screenshot* berukuran presisi ($57 \times 32\text{ cm}$).
* Dilengkapi **Export Summary Modal** yang menampilkan peringatan pra-unduh jika terdapat skenario berstatus `UNTESTED` atau `FAILED` di dalam proyek yang dipilih.
* Endpoint secara ketat divalidasi dengan `current_user.id` untuk mencegah kebocoran dokumen rahasia lintas akun.

### FR-7: Reusable Scenario Architecture & Smart Assert
* Dukungan perintah `INCLUDE_SCENARIO` untuk menyisipkan skenario tes lain sebagai sub-langkah. Dilengkapi dengan **Circular Dependency Safeguard** untuk mencegah *infinite loop*.
* Dukungan perintah universal **`ASSERT`** yang dapat mendeteksi ekspresi manusiawi seperti teks, simbol matematika (`< 0`, `>= 100`), hingga deteksi warna visual elemen (`background is red`, `disabled`).

---

## 5. Directory & Package Architecture (FastAPI Best Practices)

```text
qa_webapp/
├── app/
│   ├── api/
│   │   ├── deps.py                 # Dependency Injection (get_db, get_current_user)
│   │   └── v1/
│   │       ├── auth.py             # Router Authentication & JWT Cookie Setter
│   │       ├── dashboard.py        # Router Dashboard, Project & Skenario (Data Isolated)
│   │       ├── export.py           # Router Ekspor Laporan UT & Export Modal
│   │       └── media.py            # Router Streaming Video HTTP 206
│   ├── core/
│   │   ├── config.py               # Pydantic Settings (DB URL, JWT Secret Key)
│   │   ├── database.py             # SQLAlchemy Async Engine & Session
│   │   └── security.py             # Pure bcrypt Password Hashing & JWT Core Engine
│   ├── engine/
│   │   ├── executor.py             # Playwright Executor, Error Handling & Video Temp Handler
│   │   └── handlers.py             # Playwright Command Registries & Smart Assert
│   ├── models/
│   │   └── models.py               # SQLAlchemy ORM Models (User, Project, TestCase, dll.)
│   ├── schemas/
│   │   └── schemas.py              # Pydantic Schemas (DTO)
│   ├── services/
│   │   └── export_service.py       # Logika Penyusunan Document UT & OpenPyXL Generator
│   ├── seeders.py                  # Seeder Admin User, Default Project & Command Dictionary
│   └── main.py                     # Entrypoint & Exception Handler (RequiresLoginException)
├── static/
│   ├── videos/                     # Output Rekaman Video (.mp4) & Temp Files
│   └── screenshots/                # Output Screenshots (.png)
├── templates/
│   ├── login.html                  # Halaman UI Authentication Tailwind
│   ├── index.html                  # Main Layout, User Greeting & Logout
│   └── partials/
│       ├── project_modal.html      # Modal Buat/Edit Proyek
│       ├── export_modal.html       # Modal Ringkasan Status Ekspor
│       ├── right_panel.html        # Detail Skenario, Pre-Run Record Toggle, UT Metadata
│       ├── step_list.html          # Tabel Steps dengan Aksi Reorder (Naik/Turun), Edit, Delete
│       ├── step_edit_form.html     # Inline Edit Form Step
│       └── status.html             # Video Player, Error Log, & Aksi Video (Keep/Delete/Download)
├── init_db.py                      # Database Initialization & Admin Seeding Runner
├── .gitignore
├── requirements.txt
└── prd.md                          # Product Requirement Document