import uuid
import os
import sys
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks, Depends, Form, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

# FIX KHUSUS WINDOWS: Paksa asyncio menggunakan ProactorEventLoop agar Playwright subprocess dapat berjalan
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.database import get_db
from app.models import TestCase, TestStep, TestRun, CommandDefinition
from app.engine import run_test_scenario

app = FastAPI(title="QA Automata HTMX")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

VIDEO_DIR = "static/videos"

# ==========================================
# 0. STREAMING VIDEO ENDPOINT (HTTP 206 RANGE REQUESTS)
# ==========================================

@app.get("/videos/{video_name}")
async def stream_video(video_name: str, request: Request):
    """
    Endpoint khusus pemutaran video dengan dukungan HTTP 206 Partial Content (Range Requests).
    """
    video_path = os.path.join(VIDEO_DIR, video_name)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="File video tidak ditemukan")

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("range")

    if not range_header:
        def iterfile():
            with open(video_path, mode="rb") as f:
                yield from f
        return StreamingResponse(
            iterfile(),
            media_type="video/webm",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
        )

    try:
        unit, range_spec = range_header.split("=")
        if unit.strip() != "bytes":
            raise ValueError()
        start_str, end_spec = range_spec.split("-")
        start = int(start_str) if start_str else 0
        end = int(end_spec) if end_spec else file_size - 1
    except ValueError:
        raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")

    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")

    chunk_size = (end - start) + 1

    def iterfile():
        with open(video_path, mode="rb") as f:
            f.seek(start)
            bytes_read = 0
            while bytes_read < chunk_size:
                read_size = min(1024 * 1024, chunk_size - bytes_read)
                data = f.read(read_size)
                if not data:
                    break
                bytes_read += len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
    }

    return StreamingResponse(
        iterfile(),
        status_code=206,
        headers=headers,
        media_type="video/webm"
    )


# ==========================================
# 1. RUTE DASHBOARD SKENARIO (UTAMA)
# ==========================================

@app.get("/")
async def render_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).order_by(TestCase.id.desc()))
    test_cases = result.scalars().all()
    return templates.TemplateResponse("index.html", {
        "request": request, "title": "QA Automata - Skenario", "test_cases": test_cases
    })

@app.get("/testcase/{case_id}")
async def get_test_case_panel(case_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TestCase).where(TestCase.id == case_id).options(selectinload(TestCase.steps))
    )
    test_case = result.scalar_one_or_none()
    
    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()
    
    return templates.TemplateResponse("partials/right_panel.html", {
        "request": request, "case": test_case, "commands": commands
    })

@app.post("/testcase/new")
async def create_test_case(name: str = Form(...), base_url: str = Form(...), db: AsyncSession = Depends(get_db)):
    new_case = TestCase(name=name, base_url=base_url)
    db.add(new_case)
    await db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/testcase/{case_id}/step")
async def add_test_step(
    case_id: int,
    request: Request,
    command: str = Form(...),
    target_selector: Optional[str] = Form(None),
    input_value: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TestStep).where(TestStep.test_case_id == case_id))
    existing_steps = result.scalars().all()
    
    new_step = TestStep(
        test_case_id=case_id, 
        step_order=len(existing_steps) + 1,
        command=command, 
        target_selector=target_selector, 
        input_value=input_value
    )
    db.add(new_step)
    await db.commit()

    result_case = await db.execute(
        select(TestCase).where(TestCase.id == case_id).options(selectinload(TestCase.steps))
    )
    test_case = result_case.scalar_one()

    return templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})

@app.post("/testcase/{case_id}/run")
async def run_test(case_id: int, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    run_id = f"RUN-{str(uuid.uuid4())[:8].upper()}"
    new_run = TestRun(id=run_id, test_case_id=case_id, status="PENDING")
    db.add(new_run)
    await db.commit()

    background_tasks.add_task(run_test_scenario, run_id, case_id)
    return templates.TemplateResponse("partials/status.html", {"request": request, "run": new_run})

@app.get("/run-status/{run_id}")
async def get_run_status(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    test_run = result.scalar_one()
    return templates.TemplateResponse("partials/status.html", {"request": request, "run": test_run})

@app.post("/testcase/{case_id}/delete")
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).where(TestCase.id == case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        await db.delete(test_case)
        await db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.delete("/testcase/{case_id}/step/{step_id}")
async def delete_test_step(case_id: int, step_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id)
    )
    step = result.scalar_one_or_none()
    
    if step:
        await db.delete(step)
        await db.commit()

        remaining_result = await db.execute(
            select(TestStep)
            .where(TestStep.test_case_id == case_id)
            .order_by(TestStep.step_order.asc())
        )
        remaining_steps = remaining_result.scalars().all()
        
        for index, rem_step in enumerate(remaining_steps, start=1):
            rem_step.step_order = index
        
        await db.commit()
        
    result_case = await db.execute(
        select(TestCase).where(TestCase.id == case_id).options(selectinload(TestCase.steps))
    )
    test_case = result_case.scalar_one_or_none()

    return templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})


# ==========================================
# 2. RUTE MANAJEMEN PERINTAH (COMMANDS CRUD)
# ==========================================

@app.get("/commands")
async def render_commands_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = result.scalars().all()
    return templates.TemplateResponse("commands.html", {
        "request": request, "title": "Manajemen Perintah - QA Automata", "commands": commands
    })

@app.post("/commands/new")
async def create_command(
    request: Request,
    code: str = Form(...),
    label: str = Form(...),
    description: Optional[str] = Form(None),
    requires_selector: bool = Form(False),
    requires_value: bool = Form(False),
    placeholder_selector: Optional[str] = Form(None),
    placeholder_value: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    new_cmd = CommandDefinition(
        code=code.upper().strip(),
        label=label.strip(),
        description=description,
        requires_selector=requires_selector,
        requires_value=requires_value,
        placeholder_selector=placeholder_selector,
        placeholder_value=placeholder_value
    )
    db.add(new_cmd)
    await db.commit()

    result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = result.scalars().all()
    return templates.TemplateResponse("partials/command_table.html", {"request": request, "commands": commands})

@app.get("/commands/{cmd_id}/edit")
async def get_edit_command_modal(cmd_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CommandDefinition).where(CommandDefinition.id == cmd_id))
    cmd = result.scalar_one_or_none()
    return templates.TemplateResponse("partials/command_edit_modal.html", {"request": request, "cmd": cmd})

@app.post("/commands/{cmd_id}/edit")
async def update_command(
    cmd_id: int,
    request: Request,
    code: str = Form(...),
    label: str = Form(...),
    description: Optional[str] = Form(None),
    requires_selector: bool = Form(False),
    requires_value: bool = Form(False),
    placeholder_selector: Optional[str] = Form(None),
    placeholder_value: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(CommandDefinition).where(CommandDefinition.id == cmd_id))
    cmd = result.scalar_one_or_none()
    
    if cmd:
        cmd.code = code.upper().strip()
        cmd.label = label.strip()
        cmd.description = description
        cmd.requires_selector = requires_selector
        cmd.requires_value = requires_value
        cmd.placeholder_selector = placeholder_selector
        cmd.placeholder_value = placeholder_value
        await db.commit()

    result_all = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = result_all.scalars().all()
    return templates.TemplateResponse("partials/command_table.html", {"request": request, "commands": commands})

@app.delete("/commands/{cmd_id}")
async def delete_command(cmd_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CommandDefinition).where(CommandDefinition.id == cmd_id))
    cmd = result.scalar_one_or_none()
    
    if cmd:
        await db.delete(cmd)
        await db.commit()

    result_all = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = result_all.scalars().all()
    return templates.TemplateResponse("partials/command_table.html", {"request": request, "commands": commands})