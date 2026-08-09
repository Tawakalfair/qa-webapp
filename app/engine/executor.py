import os
import sys
import asyncio
from typing import Set
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from playwright.async_api import async_playwright

from app.core.config import settings
from app.models.models import TestCase, TestStep, TestRun
from app.engine.handlers import execute_single_command


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
    thread_engine = create_async_engine(settings.DATABASE_URL)
    ThreadSession = sessionmaker(thread_engine, class_=AsyncSession, expire_on_commit=False)

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
            await thread_engine.dispose()
            return

        videos_dir = os.path.join("static", "videos")
        os.makedirs(videos_dir, exist_ok=True)

        video_file_name = f"temp_{run_id}.mp4" if record_video else None
        relative_video_path = f"/static/videos/{video_file_name}" if record_video else None

        page = None
        context = None
        browser = None

        # PLAYWRIGHT MEMBUNGKUS SERTA MENJAGA KONEKSI ENGINE DRIVER
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
                
                context_options = {"viewport": {"width": 1280, "height": 720}}
                if record_video:
                    context_options["record_video_dir"] = videos_dir
                    context_options["record_video_size"] = {"width": 1280, "height": 720}

                context = await browser.new_context(**context_options)
                context.set_default_timeout(15000)
                context.set_default_navigation_timeout(15000)

                page = await context.new_page()

                # Eksekusi alur tes
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

                await context.close()
                await browser.close()

                if record_video and page and page.video:
                    original_video_path = await page.video.path()
                    target_video_path = os.path.join(videos_dir, video_file_name)
                    if original_video_path and os.path.exists(original_video_path):
                        if os.path.exists(target_video_path):
                            os.remove(target_video_path)
                        os.rename(original_video_path, target_video_path)

                test_run.status = "SUCCESS"
                test_run.video_url = relative_video_path if record_video else None
                test_run.error_log = None

            except Exception as e:
                error_msg = "Eksekusi tes dibatalkan karena melebihi batas waktu maksimal (Timeout 60 detik)." if isinstance(e, asyncio.TimeoutError) else str(e)
                
                saved_video_url = None
                try:
                    if context:
                        await context.close()
                    if browser:
                        await browser.close()

                    if record_video and page and page.video:
                        original_video_path = await page.video.path()
                        target_video_path = os.path.join(videos_dir, video_file_name)
                        if original_video_path and os.path.exists(original_video_path):
                            if os.path.exists(target_video_path):
                                os.remove(target_video_path)
                            os.rename(original_video_path, target_video_path)
                            saved_video_url = relative_video_path
                except Exception as vid_err:
                    print(f"[Save Failed Video Error]: {vid_err}")

                test_run.status = "FAILED"
                test_run.error_log = error_msg
                test_run.video_url = saved_video_url

            finally:
                # DIJAMIN BERHASIL DICOMMIT KE DATABASE SINKRON HTMX
                await db.commit()

        await thread_engine.dispose()


def run_test_scenario(run_id: str, case_id: int, record_video: bool = True):
    """Worker task terisolasi dengan ProactorEventLoopPolicy di Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(_async_run_test_scenario(run_id, case_id, record_video))