# 📄 Product Requirements Document (PRD) - QA Automata

**Nama Produk:** QA Automata  
**Penulis:** Mochammad Iqbal Tawaqal  
**Organisasi/Perusahaan:** NSSOL Indonesia  
**Tanggal Update:** 26 Juli 2026  
**Versi Dokumen:** v2.0 (FastAPI + HTMX + Playwright + FFmpeg Engine)  
**Status:** In Development / Production Ready (Local Intranet)  

---

## 1. Ringkasan Eksekutif (Executive Summary)

**QA Automata** adalah platform dashboard berbasis web untuk memfasilitasi pembuatan, pengelolaan, dan eksekusi skenario pengujian UI (*User Interface*) secara otomatis tanpa kode (*Low-Code / No-Code Approach*). 

Aplikasi ini menggunakan arsitektur **Server-Side Rendering (SSR) berbasis HTMX** yang dipadukan dengan **FastAPI (Python 3.12)**. Di latar belakang, eksekusi dilakukan oleh mesin **Playwright** secara asinkron (*Background Tasks*) dengan skema **Command Handler Pattern**. Sesi pengujian direkam dan otomatis dikonversi menggunakan **FFmpeg** menjadi berkas MP4 (H.264) untuk langsung dapat diputar di browser web tanpa kendala *playback*.

---

## 2. Tujuan dan Sasaran (Goals & Objectives)

* **Pengujian Low-Code:** Memungkinkan tim QA dan pengembang menyusun urutan instruksi tes visual melalui antarmuka web tanpa harus menulis skrip kode dari awal.
* **Arsitektur Modular & Extensible:** Memisahkan katalog perintah (*Master Data Command*) dari logika engine sehingga penambahan instruksi Playwright baru dapat dilakukan dengan sangat mudah.
* **Bukti Visual Nyata (Video Playback):** Merekam setiap sesi pengujian dan menyajikan video MP4 hasil pengujian di halaman web secara *real-time*.
* **Performa Tinggi & Tanpa Reload:** Memanfaatkan **HTMX** untuk pembaruan komponen UI (*HTML Fragments*) secara asinkron tanpa memuat ulang (*reload*) halaman.
* **Aksesibilitas Jaringan Internal:** Berjalan di lingkungan intranet lokal untuk menguji aplikasi web *staging/internal* yang berada di balik *firewall* perusahaan.

---

## 3. Ruang Lingkup Sistem (System Scope)

### In-Scope (Sudah Terimplementasi)
* **Manajemen Skenario Tes (`TestCase`):** Pembuatan, pemilihan, dan penghapusan skenario tes beserta Base URL.
* **Manajemen Langkah Pengujian (`TestStep`):**
  * Penyusunan langkah berbasis tabel interaktif Tailwind CSS.
  * *Dropdown* perintah dinamis yang dibaca langsung dari database.
  * Penghapusan langkah secara *real-time* via HTMX dengan pengurutan nomor (*step_order*) otomatis.
* **Manajemen Katalog Perintah Master (`/commands`):**
  * Halaman khusus CRUD (Create, Read, Update via HTMX Modal, Delete) untuk daftar perintah Playwright (`CommandDefinition`).
* **Mesin Eksekusi Playwright Asinkron:**
  * Eksekutor berbasis *Command Handler / Registry Pattern* (`app/handlers.py`).
  * Penggabungan URL otomatis (*relative path* `/path` + Base URL) via `urllib.parse.urljoin`.
* **Pemrosesan Video Rekaman:**
  * Perekaman otomatis sesi browser Playwright (.webm).
  * Konversi otomatis WebM ke MP4 (H.264) + FastStart menggunakan pemanggilan `ffmpeg` CLI.
  * Penayangan video hasil tes di UI menggunakan tag `<video>` HTML5.
* **Real-time Polling Status:** Polling status eksekusi otomatis tiap 1.5 detik via HTMX (`hx-trigger="every 1.5s"`).

### Out-of-Scope (Fase Pengembangan Selanjutnya)
* Integrasi CI/CD Pipeline (Jenkins, GitLab CI, GitHub Actions).
* Eksekusi paralel multi-thread/multi-worker.
* Perekaman instruksi otomatis via Ekstensi Browser (Browser Extension Recorder).
* Sistem Otentikasi/Otorisasi Pengguna (Multi-user RBAC).

---

## 4. Kebutuhan Fungsional Detail (Functional Requirements)

### 4.1 Modul Dashboard & Skenario (`/`)
* **REQ-01:** Pengguna dapat membuat Skenario Tes baru dengan nama skenario dan Base URL.
* **REQ-02:** Pengguna dapat memilih skenario untuk melihat detail dan urutan langkah instruksinya pada panel kanan.
* **REQ-03:** Pengguna dapat menambah langkah instruksi baru. Pilihan *command* diambil secara dinamis dari tabel `command_definitions`.
* **REQ-04:** Urutan langkah ditampilkan dalam bentuk **Tabel Modern Tailwind CSS** lengkap dengan *badge* berwarna untuk setiap jenis perintah.
* **REQ-05:** Pengguna dapat menghapus langkah tertentu (`DELETE /testcase/{case_id}/step/{step_id}`) yang akan memicu penyusunan ulang nomor urut (`step_order`) secara otomatis.

### 4.2 Modul Katalog Perintah Master (`/commands`)
* **REQ-06:** Menyediakan halaman terpisah untuk mengelola katalog perintah master Playwright.
* **REQ-07:** Pengguna dapat menambah perintah baru (*Code*, *Label*, *Description*, *Requires Selector*, *Requires Value*, *Placeholder Selector*, *Placeholder Value*).
* **REQ-08:** Pengguna dapat mengedit perintah melalui **Modal Dialog HTMX Interaktif** (`GET /commands/{id}/edit`).
* **REQ-09:** Pengguna dapat menghapus perintah dari katalog master secara *real-time*.

### 4.3 Modul Mesin Eksekusi & Handlers (`app/engine.py` & `app/handlers.py`)
* **REQ-10:** Tombol "▶ Jalankan Tes" memicu tugas latar belakang (*BackgroundTasks*) secara asinkron tanpa mengunci antarmuka web.
* **REQ-11:** Logika perintah terisolasi di `app/handlers.py` menggunakan dekorator `@register("COMMAND_NAME")`.
* **REQ-12:** Mesin Playwright menjalankan browser dalam mode *headless* dan merekam video aktivitas layar.
* **REQ-13:** Dukungan penggabungan URL cerdas pada perintah `GOTO_URL` (mendukung relative path `/login` maupun URL lengkap).

### 4.4 Modul Pemrosesan Video & Pelaporan
* **REQ-14:** Setelah sesi browser ditutup, berkas WebM mentah dikonversi oleh fungsi `convert_webm_to_mp4()` menggunakan `ffmpeg` dengan opsi `-c:v libx264 -preset ultrafast -movflags +faststart`.
* **REQ-15:** Berkas MP4 disimpan di direktori `static/videos/{run_id}.mp4` dan file WebM mentah dihapus untuk efisiensi penyimpanan.
* **REQ-16:** Setelah eksekusi selesai, UI menampilkan status (✅ LULUS / ❌ GAGAL) beserta pemutar video HTML5 MP4 yang siap diputar.

---

## 5. Arsitektur dan Teknologi (Tech Stack)

* **Bahasa Pemrograman:** Python 3.12
* **Web Framework:** FastAPI (v0.110.0)
* **Frontend Dynamic Engine:** HTMX (v1.9.10) — Menggantikan logika JavaScript kompleks dengan *HTML Fragments*.
* **Templating Engine:** Jinja2 (v3.1.3)
* **CSS Framework:** Tailwind CSS (via CDN)
* **Automation Engine:** Playwright for Python (v1.42.0)
* **Video Converter:** FFmpeg CLI (System Level Dependency)
* **Database Engine:** SQLite
* **Database Driver & ORM:** SQLAlchemy (v2.0+) Async Session (`aiosqlite`) dengan konfigurasi `expire_on_commit=False`.

---

## 6. Model Data Inti (Core Data Model)

### 1. Tabel `command_definitions` (Master Katalog Perintah)
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Primary Key. |
| `code` | String (Unique) | Kode unik perintah, misal: `GOTO_URL`, `CLICK`, `SCROLL_RIGHT`. |
| `label` | String | Nama terpisah untuk UI, misal: "Gulir ke Kanan". |
| `description` | String | Penjelasan singkat fungsi perintah. |
| `requires_selector` | Boolean | Menandakan apakah perintah butuh Target Selector (CSS/ID). |
| `requires_value` | Boolean | Menandakan apakah perintah butuh Input Value. |
| `placeholder_selector`| String | Petunjuk contoh selector di UI. |
| `placeholder_value` | String | Petunjuk contoh nilai input di UI. |

### 2. Tabel `test_cases` (Skenario Pengujian)
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Primary Key. |
| `name` | String | Nama Skenario Tes. |
| `base_url` | String | URL Dasar target pengujian. |
| `created_at` | DateTime | Waktu pembuatan skenario. |

### 3. Tabel `test_steps` (Langkah Pengujian Sekuensial)
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Primary Key. |
| `test_case_id` | Foreign Key | Merujuk ke `test_cases.id`. |
| `step_order` | Integer | Nomor urut eksekusi (1, 2, 3, dst). |
| `command` | String | Kode perintah Playwright (merujuk ke `command_definitions.code`). |
| `target_selector` | String | Alamat elemen HTML target (opsional). |
| `input_value` | String | Nilai parameter/input teks (opsional). |

### 4. Tabel `test_runs` (Riwayat Eksekusi Tes)
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | String (PK) | ID Unik Eksekusi, contoh: `RUN-23746E83`. |
| `test_case_id` | Foreign Key | Merujuk ke `test_cases.id`. |
| `status` | String | Status eksekusi (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`). |
| `video_url` | String | Path URL relatif file video MP4 hasil rekaman. |
| `error_log` | String | Catatan pesan error jika pengujian gagal. |
| `executed_at` | DateTime | Waktu eksekusi pengujian. |

---

## 7. Katalog Perintah Terdaftar di Engine (`app/handlers.py`)

1. **`GOTO_URL`**: Membuka URL utama atau relative path (misal: `/user/profile`).
2. **`CLICK`**: Mengklik elemen target berdasarkan CSS/ID/Text.
3. **`DOUBLE_CLICK`**: Melakukan klik ganda pada elemen target.
4. **`RIGHT_CLICK`**: Melakukan klik kanan pada elemen target.
5. **`TYPE_TEXT`**: Mengisi formulir teks.
6. **`PRESS_KEY`**: Menekan tombol khusus keyboard (Enter, Tab, Escape).
7. **`HOVER`**: Mengarahkan kursor mouse ke elemen target.
8. **`SELECT_OPTION`**: Memilih opsi pada elemen dropdown `<select>`.
9. **`SCROLL_RIGHT`**: Menggulir kontainer spesifik atau layar ke kanan (sejumlah piksel, misal: `300`).
10. **`SCROLL_DOWN`**: Menggulir kontainer spesifik atau layar ke bawah (sejumlah piksel, misal: `500`).
11. **`WAIT`**: Menunda eksekusi selama beberapa detik.
12. **`VERIFY_TEXT`**: Memastikan teks tertentu terdapat pada elemen target.

---

## 8. Lingkungan & Batasan Sistem (Environment & Constraints)

* **Deployment Environment:** Dijalankan secara lokal di PC remote kantor (distribusi Linux berbasis Arch / CachyOS / Ubuntu).
* **Dependensi Sistem Wajib:**
  * Virtual Environment Python 3.12 (`.venv`).
  * Binary Browser Chromium Playwright (`playwright install chromium`).
  * FFmpeg CLI Tool (`sudo apt install ffmpeg` / `sudo pacman -S ffmpeg`).
* **Manajemen Penyimpanan:** Administrator PC lokal disarankan melakukan pembersihan rutin pada folder `static/videos/` secara berkala untuk menjaga kapasitas media penyimpanan fisik.