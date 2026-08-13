import os
import sys
import asyncio
import subprocess
from typing import Set
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from playwright.async_api import async_playwright

from app.core.config import settings
from app.models.models import TestCase, TestStep, TestRun
from app.engine.handlers import execute_single_command


def optimize_video_faststart(input_path: str, output_path: str) -> bool:
    """
    Mengonversi WebM Playwright menjadi MP4 H.264 + Faststart secara kilat
    agar video lancar diputar dan di-skip di peramban web.
    """
    if not input_path or not os.path.exists(input_path):
        return False

    temp_output = output_path + ".tmp.mp4" if input_path == output_path else output_path

    try:
        # Perintah FFmpeg dengan konversi codec H.264 + ultrafast
        command = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", "libx264",        # Konversi video ke H.264 (kompatibel MP4)
            "-preset", "ultrafast",   # Proses konversi kilat dalam hitungan milidetik
            "-c:a", "aac",            # Konversi audio ke AAC
            "-movflags", "+faststart", # Pindahkan metadata ke awal file
            temp_output
        ]
        
        # Jalankan FFmpeg di background
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if temp_output != output_path:
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_output, output_path)

        if os.path.exists(input_path) and input_path != output_path:
            os.remove(input_path)
            
        return True
    except Exception as e:
        print(f"[FFmpeg Faststart Warning]: {e}. Menggunakan fallback rename biasa.")
        if temp_output != output_path and os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except Exception:
                pass
        return False


async def execute_steps_recursively(
    db, 
    page, 
    case_id: int, 
    visited_cases: Set[int], 
    base_url: str,
    run_id: str
):
    if case_id in visited_cases:
        raise ValueError(
            f"Terdeteksi Circular Dependency pada INCLUDE_SCENARIO! "
            f"Skenario ID {case_id} dipanggil berulang kali."
        )

    current_visited = set(visited_cases)
    current_visited.add(case_id)

    result = await db.execute(
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.steps))
    )
    test_case = result.scalar_one_or_none()
    
    if not test_case:
        raise ValueError(f"Skenario dengan ID {case_id} tidak ditemukan.")

    sorted_steps = sorted(test_case.steps, key=lambda s: s.step_order)

    for step in sorted_steps:
        if step.command == "INCLUDE_SCENARIO":
            if not step.input_value or not step.input_value.strip().isdigit():
                raise ValueError("INCLUDE_SCENARIO membutuhkan ID Skenario Target.")
            
            target_case_id = int(step.input_value.strip())
            await execute_steps_recursively(
                db=db,
                page=page,
                case_id=target_case_id,
                visited_cases=current_visited,
                base_url=base_url,
                run_id=run_id
            )
        else:
            await execute_single_command(page, step, base_url, run_id=run_id)


async def _async_run_test_scenario(run_id: str, case_id: int, record_video: bool = True):
    # Buat engine lokal khusus untuk thread ini agar terisolasi dari event loop Uvicorn
    thread_engine = create_async_engine(settings.DATABASE_URL)
    ThreadSession = sessionmaker(thread_engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with ThreadSession() as db:
            result_run = await db.execute(select(TestRun).where(TestRun.id == run_id))
            test_run = result_run.scalar_one()
            test_run.status = "RUNNING"
            await db.commit()

            result_case = await db.execute(select(TestCase).where(TestCase.id == case_id))
            main_case = result_case.scalar_one_or_none()

            if not main_case:
                test_run.status = "FAILED"
                test_run.error_log = "Skenario utama tidak ditemukan."
                await db.commit()
                return

            videos_dir = os.path.join("static", "videos")
            os.makedirs(videos_dir, exist_ok=True)

            video_file_name = f"temp_{run_id}.mp4" if record_video else None
            relative_video_path = f"/stream-video/{video_file_name}" if record_video else None

            page = None
            context = None
            browser = None

            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    
                    context_options = {"viewport": {"width": 1366, "height": 768}}
                    if record_video:
                        context_options["record_video_dir"] = videos_dir
                        context_options["record_video_size"] = {"width": 1366, "height": 768}

                    context = await browser.new_context(**context_options)
                    context.set_default_timeout(15000)
                    context.set_default_navigation_timeout(15000)

                    page = await context.new_page()

                    # Batasi total durasi eksekusi seluruh skenario maksimal 60 detik
                    await asyncio.wait_for(
                        execute_steps_recursively(
                            db=db,
                            page=page,
                            case_id=case_id,
                            visited_cases=set(),
                            base_url=main_case.base_url,
                            run_id=run_id
                        ),
                        timeout=60.0
                    )

                    # ==== JIKA SUKSES TANPA ERROR ====
                    await context.close()
                    
                    # Ambil path video mentah bawaan Playwright
                    raw_video_path = await page.video.path() if (record_video and page and page.video) else None
                    await browser.close()

                    # Olah video dengan FFmpeg (Raw Path -> Target Path)
                    if raw_video_path and os.path.exists(raw_video_path):
                        target_video_path = os.path.join(videos_dir, video_file_name)
                        # Optimasi via FFmpeg faststart
                        success = optimize_video_faststart(raw_video_path, target_video_path)
                        # Fallback: Jika FFmpeg tidak ada/gagal, ubah nama secara manual
                        if not success:
                            if os.path.exists(target_video_path):
                                os.remove(target_video_path)
                            os.rename(raw_video_path, target_video_path)

                    test_run.status = "SUCCESS"
                    test_run.video_url = relative_video_path if record_video else None
                    test_run.error_log = None
                    await db.commit()

            except Exception as e:
                # ==== JIKA ERROR ATAU TIMEOUT (ASSERT GAGAL) ====
                if isinstance(e, asyncio.TimeoutError):
                    error_msg = "Eksekusi tes dibatalkan karena melebihi batas waktu maksimal (Timeout)."
                else:
                    error_msg = str(e)
                
                try:
                    # 1. Tutup Context terlebih dahulu agar Playwright merampungkan berkas MP4 ke disk
                    if context:
                        await context.close()

                    # 2. Ambil path video mentah SETELAH context ditutup
                    raw_video_path = None
                    if record_video and page and page.video:
                        try:
                            raw_video_path = await page.video.path()
                        except Exception:
                            pass
                        
                    # 3. Tutup Browser
                    if browser:
                        await browser.close()
                    
                    # 4. Olah video error dengan FFmpeg faststart (Raw Path -> Target Path)
                    if raw_video_path and os.path.exists(raw_video_path):
                        target_video_path = os.path.join(videos_dir, video_file_name)
                        success = optimize_video_faststart(raw_video_path, target_video_path)
                        if not success:
                            if os.path.exists(target_video_path):
                                os.remove(target_video_path)
                            os.rename(raw_video_path, target_video_path)
                        
                except Exception as vid_err:
                    print(f"[Cleanup Error]: {vid_err}")
                
                # Update status database menjadi FAILED
                test_run.status = "FAILED"
                test_run.error_log = error_msg
                test_run.video_url = relative_video_path if record_video else None
                await db.commit()

    finally:
        await thread_engine.dispose()


def run_test_scenario(run_id: str, case_id: int, record_video: bool = True):
    """Worker task terisolasi dengan ProactorEventLoopPolicy di Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(_async_run_test_scenario(run_id, case_id, record_video))