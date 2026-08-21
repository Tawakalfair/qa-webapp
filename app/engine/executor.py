import os
import sys
import inspect
import asyncio
import subprocess
from datetime import datetime
from typing import Optional, Set
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from playwright.async_api import async_playwright

from app.core.config import settings
from app.models.models import TestCase, TestStep, TestRun, Project
from app.engine.handlers import execute_single_command


def optimize_video_faststart(input_path: str, output_path: str) -> bool:
    """Fast video conversion using FFmpeg with +faststart to allow instant browser seeking."""
    if not input_path or not os.path.exists(input_path):
        return False

    temp_output = output_path + ".tmp.mp4" if input_path == output_path else output_path

    try:
        command = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-c:a", "aac",
            "-movflags", "+faststart",
            temp_output
        ]
        
        subprocess.run(
            command, 
            check=True, 
            timeout=10, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        if temp_output != output_path:
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_output, output_path)

        if os.path.exists(input_path) and input_path != output_path:
            os.remove(input_path)
            
        return True
    except Exception as e:
        print(f"[FFmpeg Faststart Warning]: {e}")
        if temp_output != output_path and os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except Exception:
                pass
        return False


async def execute_steps_recursively(
    db: AsyncSession, 
    page, 
    case_id: int, 
    visited_cases: Set[int], 
    base_url: str,
    run_id: str,
    user_id: Optional[int] = None
):
    """Eksekusi seluruh langkah skenario termasuk sub-skenario secara teratur."""
    if case_id in visited_cases:
        raise ValueError(
            f"Circular Dependency detected in INCLUDE_SCENARIO! "
            f"Scenario ID {case_id} was called recursively."
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
        raise ValueError(f"Scenario ID {case_id} not found.")

    sorted_steps = sorted(test_case.steps, key=lambda s: s.step_order) if test_case.steps else []
    sig = inspect.signature(execute_single_command)

    for step in sorted_steps:
        if step.command == "INCLUDE_SCENARIO":
            if not step.input_value or not step.input_value.strip().isdigit():
                raise ValueError("INCLUDE_SCENARIO requires a valid numeric Target Scenario ID.")
            
            target_case_id = int(step.input_value.strip())
            await execute_steps_recursively(
                db=db,
                page=page,
                case_id=target_case_id,
                visited_cases=current_visited,
                base_url=base_url,
                run_id=run_id,
                user_id=user_id
            )
        else:
            call_kwargs = {}
            if "base_url" in sig.parameters:
                call_kwargs["base_url"] = base_url
            if "run_id" in sig.parameters:
                call_kwargs["run_id"] = run_id
            if "user_id" in sig.parameters:
                call_kwargs["user_id"] = user_id

            await execute_single_command(page, step, **call_kwargs)


async def _async_run_test_scenario(
    run_id: str, 
    case_id: int, 
    record_video: bool = True, 
    user_id: Optional[int] = None,
    timeout_ms: int = 30000
):
    thread_engine = create_async_engine(settings.DATABASE_URL)
    ThreadSession = sessionmaker(thread_engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with ThreadSession() as db:
            result_run = await db.execute(select(TestRun).where(TestRun.id == run_id))
            test_run = result_run.scalar_one_or_none()
            if not test_run:
                return

            test_run.status = "RUNNING"
            test_run.executed_at = datetime.utcnow()
            await db.commit()

            result_case = await db.execute(
                select(TestCase).where(TestCase.id == case_id).options(selectinload(TestCase.project))
            )
            main_case = result_case.scalar_one_or_none()

            if not main_case:
                test_run.status = "FAILED"
                test_run.error_log = "Main scenario not found."
                await db.commit()
                return

            # 🟢 LOGIKA STRUKTUR VIDEO ASLI MILIK ANDA
            owner_user_id = user_id or (main_case.project.user_id if main_case.project else None)
            user_folder = f"user_{owner_user_id}" if owner_user_id else "common"

            videos_dir = os.path.join("static", "videos", user_folder)
            os.makedirs(videos_dir, exist_ok=True)

            video_file_name = f"temp_{run_id}.mp4" if record_video else None
            
            # 🟢 ENDPOINT STREAMING VIDEO DENGAN DUKUNGAN HTTP 206 (SEEKABLE)
            relative_video_path = (
                f"/stream-video/{owner_user_id}/{video_file_name}" 
                if (record_video and owner_user_id) 
                else (f"/stream-video/{video_file_name}" if record_video else None)
            )

            playwright_obj = None
            browser = None
            context = None
            page = None
            raw_video_path = None

            try:
                playwright_obj = await async_playwright().start()
                browser = await playwright_obj.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )

                context_options = {
                    "viewport": {"width": 1366, "height": 768},
                    "ignore_https_errors": True,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                if record_video:
                    context_options["record_video_dir"] = videos_dir
                    context_options["record_video_size"] = {"width": 1366, "height": 768}

                context = await browser.new_context(**context_options)
                context.set_default_timeout(timeout_ms)
                context.set_default_navigation_timeout(timeout_ms)

                page = await context.new_page()
                page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

                # Eksekusi langkah
                await asyncio.wait_for(
                    execute_steps_recursively(
                        db=db,
                        page=page,
                        case_id=case_id,
                        visited_cases=set(),
                        base_url=main_case.base_url or "",
                        run_id=run_id,
                        user_id=owner_user_id
                    ),
                    timeout=180.0
                )

                # Tutup page & context agar file video selesai ditulis oleh Chromium
                if page and record_video and page.video:
                    raw_video_path = await page.video.path()

                await context.close()
                await browser.close()
                await playwright_obj.stop()

                # 🟢 PROSES FASTSTART AGAR VIDEO BISA DI-SEEK / FAST-FORWARD
                if raw_video_path and os.path.exists(raw_video_path):
                    target_video_path = os.path.join(videos_dir, video_file_name)
                    success = optimize_video_faststart(raw_video_path, target_video_path)
                    if not success:
                        if os.path.exists(target_video_path):
                            os.remove(target_video_path)
                        os.rename(raw_video_path, target_video_path)

                test_run.status = "SUCCESS"
                test_run.video_url = relative_video_path if record_video else None
                test_run.error_log = None
                await db.commit()

            except Exception as e:
                error_msg = "Eksekusi tes melebihi batas waktu maksimal (Timeout)." if isinstance(e, asyncio.TimeoutError) else str(e)
                print(f"[Executor Case #{case_id} Failed]: {error_msg}")

                try:
                    if page and record_video and page.video:
                        try:
                            raw_video_path = await page.video.path()
                        except Exception:
                            raw_video_path = None

                    if context:
                        await context.close()
                    if browser:
                        await browser.close()
                    if playwright_obj:
                        await playwright_obj.stop()

                    if raw_video_path and os.path.exists(raw_video_path):
                        target_video_path = os.path.join(videos_dir, video_file_name)
                        success = optimize_video_faststart(raw_video_path, target_video_path)
                        if not success:
                            if os.path.exists(target_video_path):
                                os.remove(target_video_path)
                            os.rename(raw_video_path, target_video_path)
                except Exception as clean_err:
                    print(f"[Cleanup Error]: {clean_err}")

                test_run.status = "FAILED"
                test_run.error_log = error_msg
                test_run.video_url = relative_video_path if record_video else None
                await db.commit()

    finally:
        await thread_engine.dispose()


def run_test_scenario(run_id: str, case_id: int, record_video: bool = True, user_id: Optional[int] = None):
    """Isolated worker task with user_id context."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(_async_run_test_scenario(run_id, case_id, record_video, user_id))