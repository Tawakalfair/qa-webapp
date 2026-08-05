import uuid
from typing import Optional
from fastapi import APIRouter, Request, BackgroundTasks, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.models import TestCase, TestStep, TestRun, CommandDefinition
from app.engine.executor import run_test_scenario

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def render_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).order_by(TestCase.id.desc()))
    test_cases = result.scalars().all()
    return templates.TemplateResponse("index.html", {
        "request": request, "title": "QA Automata - Skenario", "test_cases": test_cases
    })

@router.get("/testcase/{case_id}")
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

@router.post("/testcase/new")
async def create_test_case(name: str = Form(...), base_url: str = Form(...), db: AsyncSession = Depends(get_db)):
    new_case = TestCase(name=name, base_url=base_url)
    db.add(new_case)
    await db.commit()
    return RedirectResponse(url="/", status_code=303)

@router.post("/testcase/{case_id}/step")
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

@router.post("/testcase/{case_id}/run")
async def run_test(case_id: int, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    run_id = f"RUN-{str(uuid.uuid4())[:8].upper()}"
    new_run = TestRun(id=run_id, test_case_id=case_id, status="PENDING")
    db.add(new_run)
    await db.commit()

    background_tasks.add_task(run_test_scenario, run_id, case_id)
    return templates.TemplateResponse("partials/status.html", {"request": request, "run": new_run})

@router.get("/run-status/{run_id}")
async def get_run_status(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    test_run = result.scalar_one()
    return templates.TemplateResponse("partials/status.html", {"request": request, "run": test_run})

@router.post("/testcase/{case_id}/delete")
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).where(TestCase.id == case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        await db.delete(test_case)
        await db.commit()
    return RedirectResponse(url="/", status_code=303)

@router.delete("/testcase/{case_id}/step/{step_id}")
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

@router.get("/testcase/{case_id}/step/{step_id}/edit")
async def get_edit_step_form(
    case_id: int,
    step_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Mengembalikan form inline edit untuk langkah tes tertentu."""
    result = await db.execute(
        select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id)
    )
    step = result.scalar_one_or_none()
    
    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    return templates.TemplateResponse("partials/step_edit_form.html", {
        "request": request, 
        "case_id": case_id, 
        "step": step, 
        "commands": commands
    })

@router.post("/testcase/{case_id}/step/{step_id}/edit")
async def update_test_step(
    case_id: int,
    step_id: int,
    request: Request,
    command: str = Form(...),
    target_selector: Optional[str] = Form(None),
    input_value: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Memperbarui data langkah tes dan merender ulang tabel daftar langkah."""
    result = await db.execute(
        select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id)
    )
    step = result.scalar_one_or_none()
    
    if step:
        step.command = command
        step.target_selector = target_selector
        step.input_value = input_value
        await db.commit()

    result_case = await db.execute(
        select(TestCase).where(TestCase.id == case_id).options(selectinload(TestCase.steps))
    )
    test_case = result_case.scalar_one_or_none()

    return templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})