import json
import uuid
import os
from typing import Optional
from fastapi import APIRouter, Request, BackgroundTasks, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.models import TestCase, TestStep, TestRun, CommandDefinition, Project
from app.engine.executor import run_test_scenario
from fastapi.responses import StreamingResponse
from app.services.export_service import generate_ut_matrix_excel

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")


# Helper untuk menyisipkan header HTMX Toast Notification
def trigger_toast(response_obj: Response, message: str, toast_type: str = "success") -> Response:
    response_obj.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": message, "type": toast_type}
    })
    return response_obj


# ==========================================
# 1. RUTE DASHBOARD & FILTER SKENARIO
# ==========================================

@router.get("/")
async def render_dashboard(
    request: Request,
    project_id: Optional[str] = None,
    test_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    parsed_project_id: Optional[int] = None
    if project_id and project_id.strip().isdigit():
        parsed_project_id = int(project_id.strip())

    proj_result = await db.execute(select(Project).order_by(Project.name.asc()))
    projects = proj_result.scalars().all()

    query = (
        select(TestCase)
        .options(selectinload(TestCase.project), selectinload(TestCase.runs), selectinload(TestCase.steps))
        .order_by(TestCase.id.desc())
    )
    
    if parsed_project_id:
        query = query.where(TestCase.project_id == parsed_project_id)
    if test_type and test_type.strip():
        query = query.where(TestCase.test_type == test_type.strip())

    result = await db.execute(query)
    test_cases = result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "QA Automata - Skenario",
        "projects": projects,
        "test_cases": test_cases,
        "selected_project_id": parsed_project_id,
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
    new_project = Project(name=name.strip(), description=description.strip() if description else None)
    db.add(new_project)
    await db.commit()
    msg = f"Proyek '{new_project.name}' berhasil dibuat!"
    return RedirectResponse(url=f"/?project_id={new_project.id}&msg={msg}&type=success", status_code=303)


@router.post("/projects/{project_id}/edit")
async def edit_project(
    project_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if project:
        project.name = name.strip()
        project.description = description.strip() if description else None
        await db.commit()
        msg = f"Proyek '{project.name}' berhasil diperbarui!"
        return RedirectResponse(url=f"/?project_id={project_id}&msg={msg}&type=success", status_code=303)
        
    return RedirectResponse(url="/", status_code=303)


@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if project:
        name = project.name
        await db.delete(project)
        await db.commit()
        msg = f"Proyek '{name}' berhasil dihapus."
        return RedirectResponse(url=f"/?msg={msg}&type=success", status_code=303)
        
    return RedirectResponse(url="/", status_code=303)


# ==========================================
# 3. RUTE SKENARIO (TEST CASE & METADATA)
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

    # Eager load TestCase.project untuk daftar other_cases
    all_cases_result = await db.execute(
        select(TestCase)
        .where(TestCase.id != case_id)
        .options(selectinload(TestCase.project))
        .order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()
    
    return templates.TemplateResponse("partials/right_panel.html", {
        "request": request, 
        "case": test_case, 
        "commands": commands,
        "other_cases": other_cases
    })


@router.post("/testcase/new")
async def create_test_case(
    project_id: str = Form(...),
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
    if not project_id or not project_id.strip().isdigit():
        msg = "Proyek target tidak valid. Harap pilih proyek terlebih dahulu."
        return RedirectResponse(url=f"/?msg={msg}&type=error", status_code=303)

    parsed_project_id = int(project_id.strip())

    new_case = TestCase(
        project_id=parsed_project_id,
        name=name.strip(),
        base_url=base_url.strip(),
        test_type=test_type,
        reference_number=reference_number.strip() if (reference_number and reference_number.strip()) else None,
        ut_theme=ut_theme.strip() if (ut_theme and ut_theme.strip()) else None,
        ut_function_name=ut_function_name.strip() if (ut_function_name and ut_function_name.strip()) else None,
        ut_action=ut_action.strip() if (ut_action and ut_action.strip()) else None,
        ut_condition_1=ut_condition_1.strip() if (ut_condition_1 and ut_condition_1.strip()) else None,
        ut_condition_2=ut_condition_2.strip() if (ut_condition_2 and ut_condition_2.strip()) else None,
        ut_classification=ut_classification.strip() if (ut_classification and ut_classification.strip()) else None,
        ut_how_to_test=ut_how_to_test.strip() if (ut_how_to_test and ut_how_to_test.strip()) else None,
        ut_expected_results=ut_expected_results.strip() if (ut_expected_results and ut_expected_results.strip()) else None
    )
    db.add(new_case)
    await db.commit()
    
    msg = f"Skenario '{new_case.name}' berhasil ditambahkan!"
    return RedirectResponse(url=f"/?project_id={parsed_project_id}&msg={msg}&type=success", status_code=303)


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
        test_case.ut_theme = ut_theme.strip() if (ut_theme and ut_theme.strip()) else None
        test_case.ut_function_name = ut_function_name.strip() if (ut_function_name and ut_function_name.strip()) else None
        test_case.ut_action = ut_action.strip() if (ut_action and ut_action.strip()) else None
        test_case.ut_condition_1 = ut_condition_1.strip() if (ut_condition_1 and ut_condition_1.strip()) else None
        test_case.ut_condition_2 = ut_condition_2.strip() if (ut_condition_2 and ut_condition_2.strip()) else None
        test_case.ut_classification = ut_classification.strip() if (ut_classification and ut_classification.strip()) else None
        test_case.ut_how_to_test = ut_how_to_test.strip() if (ut_how_to_test and ut_how_to_test.strip()) else None
        test_case.ut_expected_results = ut_expected_results.strip() if (ut_expected_results and ut_expected_results.strip()) else None
        await db.commit()

    refreshed_case_result = await db.execute(
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.project), selectinload(TestCase.steps))
    )
    refreshed_case = refreshed_case_result.scalar_one_or_none()

    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    # Eager load TestCase.project untuk daftar other_cases
    all_cases_result = await db.execute(
        select(TestCase)
        .where(TestCase.id != case_id)
        .options(selectinload(TestCase.project))
        .order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()

    res = templates.TemplateResponse("partials/right_panel.html", {
        "request": request, 
        "case": refreshed_case, 
        "commands": commands, 
        "other_cases": other_cases
    })
    return trigger_toast(res, "Metadata UT Document berhasil diperbarui!")


@router.post("/testcase/{case_id}/delete")
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).where(TestCase.id == case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        name = test_case.name
        await db.delete(test_case)
        await db.commit()
        msg = f"Skenario '{name}' berhasil dihapus."
        return RedirectResponse(url=f"/?msg={msg}&type=success", status_code=303)
    return RedirectResponse(url="/", status_code=303)


# ==========================================
# 4. RUTE STEP EDITOR (HTMX INLINE EDIT)
# ==========================================

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
    
    if not step:
        return Response(status_code=404)

    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    # Eager load TestCase.project untuk daftar other_cases
    all_cases_result = await db.execute(
        select(TestCase)
        .where(TestCase.id != case_id)
        .options(selectinload(TestCase.project))
        .order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()

    return templates.TemplateResponse("partials/step_edit_form.html", {
        "request": request,
        "case_id": case_id,
        "step": step,
        "commands": commands,
        "other_cases": other_cases
    })

@router.get("/testcases/search")
async def search_test_cases(
    request: Request,
    q: str = "",
    current_case_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    query_str = q.strip()
    
    # Jika query kurang dari 2 karakter, kembalikan list kosong
    if len(query_str) < 2:
        return templates.TemplateResponse("partials/scenario_search_results.html", {
            "request": request,
            "test_cases": [],
            "query": query_str
        })

    # Filter pencarian berdasarkan Nama Skenario
    stmt = (
        select(TestCase)
        .options(selectinload(TestCase.project))
        .where(TestCase.name.ilike(f"%{query_str}%"))
    )

    # Biar skenario yang sedang dibuka tidak ikut muncul
    if current_case_id:
        stmt = stmt.where(TestCase.id != current_case_id)

    # Batasi HANYA 8 hasil teratas demi kecepatan & kebersihan UI
    stmt = stmt.order_by(TestCase.name.asc()).limit(8)
    
    result = await db.execute(stmt)
    test_cases = result.scalars().all()

    return templates.TemplateResponse("partials/scenario_search_results.html", {
        "request": request,
        "test_cases": test_cases,
        "query": query_str
    })

@router.post("/testcase/{case_id}/step")
async def add_test_step(
    case_id: int,
    request: Request,
    command: str = Form(...),
    target_selector: Optional[str] = Form(None),
    input_value: Optional[str] = Form(None),
    input_value_select: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TestStep).where(TestStep.test_case_id == case_id))
    existing_steps = result.scalars().all()
    
    # Ambil nilai dari input_value_select atau input_value
    final_input = input_value_select if (command == "INCLUDE_SCENARIO" and input_value_select) else input_value

    new_step = TestStep(
        test_case_id=case_id, 
        step_order=len(existing_steps) + 1,
        command=command, 
        target_selector=target_selector.strip() if (target_selector and target_selector.strip()) else None, 
        input_value=final_input.strip() if (final_input and final_input.strip()) else None
    )
    db.add(new_step)
    await db.commit()

    result_case = await db.execute(
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.project), selectinload(TestCase.steps))
    )
    test_case = result_case.scalar_one_or_none()

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, "Langkah instruksi berhasil ditambahkan!")


@router.post("/testcase/{case_id}/step/{step_id}/edit")
async def update_test_step(
    case_id: int,
    step_id: int,
    request: Request,
    command: str = Form(...),
    target_selector: Optional[str] = Form(None),
    input_value: Optional[str] = Form(None),
    input_value_select: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id)
    )
    step = result.scalar_one_or_none()
    
    final_input = input_value_select if (command == "INCLUDE_SCENARIO" and input_value_select) else input_value

    if step:
        step.command = command
        step.target_selector = target_selector.strip() if (target_selector and target_selector.strip()) else None
        step.input_value = final_input.strip() if (final_input and final_input.strip()) else None
        await db.commit()

    result_case = await db.execute(
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.project), selectinload(TestCase.steps))
    )
    test_case = result_case.scalar_one_or_none()

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, "Langkah instruksi berhasil diperbarui!")


@router.delete("/testcase/{case_id}/step/{step_id}")
async def delete_test_step(
    case_id: int, 
    step_id: int, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
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
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.project), selectinload(TestCase.steps))
    )
    test_case = result_case.scalar_one_or_none()

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, "Langkah instruksi berhasil dihapus.")


# ==========================================
# 5. RUTE EKSEKUSI PENGIJIAN
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