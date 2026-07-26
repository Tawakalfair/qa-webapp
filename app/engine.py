import asyncio
import os
import shutil
import subprocess
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from playwright.async_api import async_playwright

from app.database import SessionLocal
from app.models import TestCase, TestStep, TestRun
from app.handlers import COMMAND_REGISTRY

VIDEO_DIR = "static/videos"
os.makedirs(VIDEO_DIR, exist_ok=True)

def convert_webm_to_mp4(input_path: str, output_path: str) -> bool:
    """
    Mengonversi WebM mentah Playwright menjadi MP4 (H.264) + FastStart
    agar dapat diputar secara mulus di seluruh web browser HTML5.
    """
    try:
        cmd = [
            "ffmpeg",
            "-y",                      # Overwrite jika file sudah ada
            "-i", input_path,          # Input file webm mentah
            "-c:v", "libx264",         # Codec H.264 universal
            "-pix_fmt", "yuv420p",     # Format piksel kompatibel HTML5
            "-preset", "ultrafast",    # Konversi super cepat
            "-movflags", "+faststart", # Pindahkan metadata ke depan agar instan dimuat
            output_path
        ]
        # Jalankan proses FFmpeg
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        print(f"Warning/Error FFmpeg: {e}")
        return False

async def run_test_scenario(run_id: str, test_case_id: int):
    print(f"[RUN-{run_id}] Menghubungkan ke database...")
    
    async with SessionLocal() as db:
        result = await db.execute(
            select(TestCase)
            .where(TestCase.id == test_case_id)
            .options(selectinload(TestCase.steps))
        )
        test_case = result.scalar_one_or_none()
        
        if not test_case:
            print(f"[RUN-{run_id}] ERROR: Test Case ID {test_case_id} tidak ditemukan.")
            return

        run_result = await db.execute(select(TestRun).where(TestRun.id == run_id))
        test_run = run_result.scalar_one_or_none()
        if test_run:
            test_run.status = "RUNNING"
            await db.commit()

        steps = sorted(test_case.steps, key=lambda s: s.step_order)
        print(f"[RUN-{run_id}] Skenario '{test_case.name}' memiliki {len(steps)} langkah.")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                record_video_dir=VIDEO_DIR,
                record_video_size={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            status = "SUCCESS"
            error_log = None

            try:
                for step in steps:
                    cmd = step.command.upper()
                    print(f"[RUN-{run_id}] Step {step.step_order}: {cmd}")
                    
                    handler_func = COMMAND_REGISTRY.get(cmd)
                    if handler_func:
                        await handler_func(page, step, test_case)
                    else:
                        print(f"[RUN-{run_id}] WARNING: Perintah '{cmd}' tidak ditemukan di handlers.py.")

                await asyncio.sleep(1)

            except Exception as e:
                status = "FAILED"
                error_log = str(e)
                print(f"[RUN-{run_id}] GAGAL pada langkah ini: {e}")
                
            finally:
                video_obj = page.video

                # Tutup browser agar file WebM selesai ditulis
                await page.close()
                await context.close()
                await browser.close()

                final_video_url = None
                if video_obj:
                    try:
                        raw_webm_path = await video_obj.path()
                        if raw_webm_path and os.path.exists(raw_webm_path):
                            mp4_filename = f"{run_id}.mp4"
                            final_mp4_path = os.path.join(VIDEO_DIR, mp4_filename)

                            # Konversi WebM mentah menjadi MP4 via FFmpeg
                            success = convert_webm_to_mp4(raw_webm_path, final_mp4_path)
                            
                            if success and os.path.exists(final_mp4_path):
                                final_video_url = f"/static/videos/{mp4_filename}"
                                # Hapus file webm mentah asli agar hemat ruang penyimpanan
                                if os.path.exists(raw_webm_path):
                                    os.remove(raw_webm_path)
                            else:
                                # Fallback jika FFmpeg gagal
                                fallback_path = os.path.join(VIDEO_DIR, f"{run_id}.webm")
                                shutil.move(raw_webm_path, fallback_path)
                                final_video_url = f"/static/videos/{run_id}.webm"

                    except Exception as ve:
                        print(f"[RUN-{run_id}] Gagal memproses video: {ve}")

                if test_run:
                    test_run.status = status
                    test_run.video_url = final_video_url
                    test_run.error_log = error_log
                    await db.commit()
                    print(f"[RUN-{run_id}] Eksekusi selesai. Status: {status} | Video: {final_video_url}")