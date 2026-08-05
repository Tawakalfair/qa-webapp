import asyncio
import concurrent.futures
import os
import shutil
import subprocess
import sys
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from playwright.async_api import async_playwright

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import TestCase, TestStep, TestRun
from app.engine.handlers import COMMAND_REGISTRY

def convert_webm_to_mp4(input_path: str, output_path: str) -> bool:
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "ultrafast", "-movflags", "+faststart",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        print(f"Warning FFmpeg: {e}")
        return False

async def _async_run_test_scenario(run_id: str, test_case_id: int):
    async with SessionLocal() as db:
        result = await db.execute(
            select(TestCase)
            .where(TestCase.id == test_case_id)
            .options(selectinload(TestCase.steps))
        )
        test_case = result.scalar_one_or_none()
        if not test_case:
            return

        run_result = await db.execute(select(TestRun).where(TestRun.id == run_id))
        test_run = run_result.scalar_one_or_none()
        if test_run:
            test_run.status = "RUNNING"
            await db.commit()

        steps = sorted(test_case.steps, key=lambda s: s.step_order)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                record_video_dir=settings.VIDEO_DIR,
                record_video_size={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            status = "SUCCESS"
            error_log = None

            try:
                for step in steps:
                    cmd = step.command.upper()
                    handler_func = COMMAND_REGISTRY.get(cmd)
                    if handler_func:
                        await handler_func(page, step, test_case)

                await asyncio.sleep(1)

            except Exception as e:
                status = "FAILED"
                error_log = str(e)
                
            finally:
                video_obj = page.video
                await page.close()
                await context.close()
                await browser.close()

                final_video_url = None
                if video_obj:
                    try:
                        raw_webm_path = await video_obj.path()
                        if raw_webm_path and os.path.exists(raw_webm_path):
                            mp4_filename = f"{run_id}.mp4"
                            final_mp4_path = os.path.join(settings.VIDEO_DIR, mp4_filename)

                            success = convert_webm_to_mp4(raw_webm_path, final_mp4_path)
                            if success and os.path.exists(final_mp4_path):
                                final_video_url = f"/static/videos/{mp4_filename}"
                                if os.path.exists(raw_webm_path):
                                    os.remove(raw_webm_path)
                            else:
                                fallback_path = os.path.join(settings.VIDEO_DIR, f"{run_id}.webm")
                                shutil.move(raw_webm_path, fallback_path)
                                final_video_url = f"/static/videos/{run_id}.webm"
                    except Exception as ve:
                        print(f"Video Error: {ve}")

                if test_run:
                    test_run.status = status
                    test_run.video_url = final_video_url
                    test_run.error_log = error_log
                    await db.commit()

def _run_in_isolated_thread(run_id: str, test_case_id: int):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        new_loop.run_until_complete(_async_run_test_scenario(run_id, test_case_id))
    finally:
        new_loop.close()

async def run_test_scenario(run_id: str, test_case_id: int):
    if sys.platform == "win32":
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, _run_in_isolated_thread, run_id, test_case_id)
    else:
        await _async_run_test_scenario(run_id, test_case_id)