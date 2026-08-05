import uuid
from typing import Optional
from fastapi import APIRouter, Request, BackgroundTasks, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.models import TestCase, TestStep, TestRun, CommandDefinition, Project
from app.engine.executor import run_test_scenario

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")


# ==========================================
# 1. RUTE DASHBOARD & FILTER SKENARIO
# ==========================================

@router.get("/")
async def render_dashboard(
    request: Request,
    project_id: Optional[int] = None,
    test_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Fetch daftar seluruh proyek untuk dropdown filter
    proj_result = await db.execute(select(Project).order_by(Project.name.asc()))
    projects = proj_result.scalars().all()

    # Query TestCase dengan filter dinamis
    query = select(TestCase).options(selectinload(TestCase.project), selectinload(TestCase.runs)).order_by(TestCase.id.desc())
    
    if project_id:
        query = query.where(TestCase.project_id == project_id)
    if test_type and test_type.strip():
        query = query.where(TestCase.test_type == test_type)

    result = await db.execute(query)
    test_cases = result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "QA Automata - Skenario",
        "projects": projects,
        "test_cases": test_cases,
        "selected_project_id": project_id,
        "selected_test_type": test_type
    })


# ==========================================
# 2. RUTE MANAJEMEN PROYEK (CRUD)
# ==========================================

@router.post("/projects/new")
async def create_project(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    new_project = Project(name=name.strip(), description=description)
    db.add(new_project)
    await db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project:
        await db.delete(project)
        await db.commit()
    return RedirectResponse(url="/", status_code=303)


# ==========================================
# 3. RUTE SKENARIO (TEST CASE & UT METADATA)
# ==========================================

@router.get("/testcase/{case_id}")
async def get_test_case_panel(case_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.project), selectinload(TestCase.steps))
    )
    test_case = result.scalar_one_or_none()
    
    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()
    
    return templates.TemplateResponse("partials/right_panel.html", {
        "request": request, "case": test_case, "commands": commands
    })


@router.post("/testcase/new")
async def create_test_case(
    project_id: int = Form(...),
    name: str = Form(...),
    base_url: str = Form(...),
    test_type: str = Form("REGRESSION"),
    reference_number: Optional[str] = Form(None),
    ut_theme: Optional[str] = Form(None),
    ut_function_name: Optional[str] = Form(None),
    ut_action: Optional[str] = Form(None),
    ut_condition_1: Optional[str] = Form(None),
    ut_condition_2: Optional[str] = Form(None),
    ut_classification: Optional[str] = Form(None),
    ut_how_to_test: Optional[str] = Form(None),
    ut_expected_results: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    new_case = TestCase(
        project_id=project_id,
        name=name.strip(),
        base_url=base_url.strip(),
        test_type=test_type,
        reference_number=reference_number.strip() if reference_number else None,
        ut_theme=ut_theme.strip() if ut_theme else None,
        ut_function_name=ut_function_name.strip() if ut_function_name else None,
        ut_action=ut_action.strip() if ut_action else None,
        ut_condition_1=ut_condition_1.strip() if ut_condition_1 else None,
        ut_condition_2=ut_condition_2.strip() if ut_condition_2 else None,
        ut_classification=ut_classification.strip() if ut_classification else None,
        ut_how_to_test=ut_how_to_test.strip() if ut_how_to_test else None,
        ut_expected_results=ut_expected_results.strip() if ut_expected_results else None
    )
    db.add(new_case)
    await db.commit()
    return RedirectResponse(url=f"/?project_id={project_id}", status_code=303)


@router.post("/testcase/{case_id}/edit-ut-metadata")
async def update_ut_metadata(
    case_id: int,
    request: Request,
    ut_theme: Optional[str] = Form(None),
    ut_function_name: Optional[str] = Form(None),
    ut_action: Optional[str] = Form(None),
    ut_condition_1: Optional[str] = Form(None),
    ut_condition_2: Optional[str] = Form(None),
    ut_classification: Optional[str] = Form(None),
    ut_how_to_test: Optional[str] = Form(None),
    ut_expected_results: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TestCase).where(TestCase.id == case_id))
    test_case = result.scalar_one_or_none()
    
    if test_case:
        test_case.ut_theme = ut_theme.strip() if ut_theme else None
        test_case.ut_function_name = ut_function_name.strip() if ut_function_name else None
        test_case.ut_action = ut_action.strip() if ut_action else None
        test_case.ut_condition_1 = ut_condition_1.strip() if ut_condition_1 else None
        test_case.ut_condition_2 = ut_condition_2.strip() if ut_condition_2 else None
        test_case.ut_classification = ut_classification.strip() if ut_classification else None
        test_case.ut_how_to_test = ut_how_to_test.strip() if ut_how_to_test else None
        test_case.ut_expected_results = ut_expected_results.strip() if ut_expected_results else None
        await db.commit()

    return RedirectResponse(url=f"/testcase/{case_id}", status_code=303)


@router.post("/testcase/{case_id}/delete")
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).where(TestCase.id == case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        await db.delete(test_case)
        await db.commit()
    return RedirectResponse(url="/", status_code=303)


# ==========================================
# 4. RUTE STEP EDITOR (HTMX INLINE EDIT)
# ==========================================

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


@router.get("/testcase/{case_id}/step/{step_id}/edit")
async def get_edit_step_form(
    case_id: int,
    step_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
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


# ==========================================
# 5. RUTE EKSEKUSI PENGIJIAN (PLAYWRIGHT RUNNER)
# ==========================================

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