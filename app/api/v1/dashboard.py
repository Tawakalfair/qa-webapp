import json
import uuid
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

# Import Dependency Login
from app.api.deps import get_db, get_current_user
from app.models.models import TestCase, TestStep, TestRun, CommandDefinition, Project, User
from app.engine.executor import run_test_scenario
from app.services.export_service import generate_ut_matrix_excel

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")

# Helper untuk menyisipkan header HTMX Toast Notification
def trigger_toast(response_obj: Response, message: str, toast_type: str = "success") -> Response:
    response_obj.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": message, "type": toast_type}
    })
    return response_obj

# Helper Cek Akses Skenario
async def get_user_testcase_or_404(db: AsyncSession, case_id: int, user_id: int, eager_load_steps=False, eager_load_runs=False):
    query = select(TestCase).join(Project).where(TestCase.id == case_id, Project.user_id == user_id)
    options = [selectinload(TestCase.project)]
    if eager_load_steps:
        options.append(selectinload(TestCase.steps))
    if eager_load_runs:
        options.append(selectinload(TestCase.runs))
        
    query = query.options(*options)
    result = await db.execute(query)
    test_case = result.scalar_one_or_none()
    if not test_case:
        raise HTTPException(status_code=404, detail="Skenario tidak ditemukan atau Anda tidak memiliki akses.")
    return test_case


# ==========================================
# RUTE DASHBOARD & FILTER SKENARIO
# ==========================================

@router.get("/")
async def render_dashboard(
    request: Request,
    project_id: Optional[str] = None,
    test_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # 🔒 Proteksi Login
):
    parsed_project_id: Optional[int] = None
    if project_id and project_id.strip().isdigit():
        parsed_project_id = int(project_id.strip())

    # Filter 1: Hanya tampilkan proyek milik current_user
    proj_result = await db.execute(
        select(Project).where(Project.user_id == current_user.id).order_by(Project.name.asc())
    )
    projects = proj_result.scalars().all()

    # Filter 2: Hanya tampilkan test cases dari proyek milik current_user
    query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
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
        "selected_test_type": test_type,
        "current_user": current_user  # Kirim user ke Jinja2
    })


# ==========================================
# RUTE MANAJEMEN PROYEK (CRUD)
# ==========================================

@router.post("/projects/new")
async def create_project(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ikat proyek baru dengan ID user yang sedang login
    new_project = Project(user_id=current_user.id, name=name.strip(), description=description.strip() if description else None)
    db.add(new_project)
    await db.commit()
    msg = f"Proyek '{new_project.name}' berhasil dibuat!"
    return RedirectResponse(url=f"/?project_id={new_project.id}&msg={msg}&type=success", status_code=303)


@router.post("/projects/{project_id}/edit")
async def edit_project(
    project_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Pastikan proyek milik current_user
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = result.scalar_one_or_none()
    
    if project:
        project.name = name.strip()
        project.description = description.strip() if description else None
        await db.commit()
        msg = f"Proyek '{project.name}' berhasil diperbarui!"
        return RedirectResponse(url=f"/?project_id={project_id}&msg={msg}&type=success", status_code=303)
        
    return RedirectResponse(url="/", status_code=303)


@router.post("/projects/{project_id}/delete")
async def delete_project(
    project_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = result.scalar_one_or_none()
    
    if project:
        name = project.name
        await db.delete(project)
        await db.commit()
        msg = f"Proyek '{name}' berhasil dihapus."
        return RedirectResponse(url=f"/?msg={msg}&type=success", status_code=303)
        
    return RedirectResponse(url="/", status_code=303)


# ==========================================
# RUTE SKENARIO (TEST CASE & METADATA)
# ==========================================

@router.get("/testcase/{case_id}")
async def get_test_case_panel(case_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    # Hanya ambil others cases dari project milik user
    all_cases_result = await db.execute(
        select(TestCase).join(Project).where(TestCase.id != case_id, Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.name.asc())
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not project_id or not project_id.strip().isdigit():
        msg = "Proyek target tidak valid."
        return RedirectResponse(url=f"/?msg={msg}&type=error", status_code=303)

    parsed_project_id = int(project_id.strip())

    # Keamanan: Pastikan project target milik current_user
    proj_result = await db.execute(select(Project).where(Project.id == parsed_project_id, Project.user_id == current_user.id))
    if not proj_result.scalar_one_or_none():
        return RedirectResponse(url=f"/?msg=Akses ditolak&type=error", status_code=303)

    new_case = TestCase(
        project_id=parsed_project_id, name=name.strip(), base_url=base_url.strip(), test_type=test_type,
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


@router.get("/testcase/{case_id}/edit-modal")
async def get_edit_case_modal(case_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    return templates.TemplateResponse("partials/edit_case_modal.html", {"request": {}, "case": test_case})


@router.post("/testcase/{case_id}/edit")
async def update_test_case(
    case_id: int,
    name: str = Form(...),
    base_url: str = Form(...),
    test_type: str = Form("Normal"),
    reference_number: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True, eager_load_runs=True)

    test_case.name = name.strip()
    test_case.base_url = base_url.strip()
    test_case.test_type = test_type.strip() if test_type else "Normal"
    test_case.reference_number = reference_number.strip() if reference_number else None
    await db.commit()

    # Data pendukung untuk right_panel
    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    other_cases_result = await db.execute(
        select(TestCase).join(Project).where(TestCase.id != case_id, Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.name.asc())
    )
    other_cases = other_cases_result.scalars().all()

    # OOB Swap All Cases List
    all_cases_query = select(TestCase).join(Project).where(Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.id.asc())
    if test_case.project_id:
        all_cases_query = all_cases_query.where(TestCase.project_id == test_case.project_id)
    all_cases_result = await db.execute(all_cases_query)
    all_test_cases = all_cases_result.scalars().all()

    return templates.TemplateResponse("partials/right_panel.html", {
        "request": {}, "case": test_case, "commands": commands, "other_cases": other_cases, "test_cases": all_test_cases 
    })


@router.get("/testcases/list-partial")
async def get_case_list_partial(project_id: Optional[int] = None, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(TestCase).join(Project).where(Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.id.asc())
    if project_id:
        query = query.where(TestCase.project_id == project_id)
        
    result = await db.execute(query)
    test_cases = result.scalars().all()
    return templates.TemplateResponse("partials/case_list.html", {"request": {}, "test_cases": test_cases})


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    test_case.ut_theme = ut_theme.strip() if (ut_theme and ut_theme.strip()) else None
    test_case.ut_function_name = ut_function_name.strip() if (ut_function_name and ut_function_name.strip()) else None
    test_case.ut_action = ut_action.strip() if (ut_action and ut_action.strip()) else None
    test_case.ut_condition_1 = ut_condition_1.strip() if (ut_condition_1 and ut_condition_1.strip()) else None
    test_case.ut_condition_2 = ut_condition_2.strip() if (ut_condition_2 and ut_condition_2.strip()) else None
    test_case.ut_classification = ut_classification.strip() if (ut_classification and ut_classification.strip()) else None
    test_case.ut_how_to_test = ut_how_to_test.strip() if (ut_how_to_test and ut_how_to_test.strip()) else None
    test_case.ut_expected_results = ut_expected_results.strip() if (ut_expected_results and ut_expected_results.strip()) else None
    await db.commit()

    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    all_cases_result = await db.execute(
        select(TestCase).join(Project).where(TestCase.id != case_id, Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()

    res = templates.TemplateResponse("partials/right_panel.html", {
        "request": request, "case": test_case, "commands": commands, "other_cases": other_cases
    })
    return trigger_toast(res, "Metadata UT Document berhasil diperbarui!")


@router.post("/testcase/{case_id}/delete")
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    name = test_case.name
    await db.delete(test_case)
    await db.commit()
    msg = f"Skenario '{name}' berhasil dihapus."
    return RedirectResponse(url=f"/?msg={msg}&type=success", status_code=303)


# ==========================================
# RUTE STEP EDITOR & EKSEKUSI
# ==========================================
@router.get("/testcase/{case_id}/step/{step_id}/edit")
async def get_edit_step_form(case_id: int, step_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await get_user_testcase_or_404(db, case_id, current_user.id)  # Validate access
    
    result = await db.execute(select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id))
    step = result.scalar_one_or_none()
    if not step: return Response(status_code=404)

    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    all_cases_result = await db.execute(
        select(TestCase).join(Project).where(TestCase.id != case_id, Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()

    return templates.TemplateResponse("partials/step_edit_form.html", {
        "request": request, "case_id": case_id, "step": step, "commands": commands, "other_cases": other_cases
    })


@router.get("/testcases/search")
async def search_test_cases(request: Request, q: str = "", current_case_id: Optional[int] = None, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query_str = q.strip()
    if len(query_str) < 2:
        return templates.TemplateResponse("partials/scenario_search_results.html", {"request": request, "test_cases": [], "query": query_str})

    stmt = select(TestCase).join(Project).options(selectinload(TestCase.project)).where(TestCase.name.ilike(f"%{query_str}%"), Project.user_id == current_user.id)
    if current_case_id:
        stmt = stmt.where(TestCase.id != current_case_id)
        
    stmt = stmt.order_by(TestCase.name.asc()).limit(8)
    result = await db.execute(stmt)
    return templates.TemplateResponse("partials/scenario_search_results.html", {"request": request, "test_cases": result.scalars().all(), "query": query_str})


@router.post("/testcase/{case_id}/step")
async def add_test_step(case_id: int, request: Request, command: str = Form(...), target_selector: Optional[str] = Form(None), input_value: Optional[str] = Form(None), input_value_select: Optional[str] = Form(None), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    existing_steps = test_case.steps
    final_input = input_value_select if (command == "INCLUDE_SCENARIO" and input_value_select) else input_value
    new_step = TestStep(test_case_id=case_id, step_order=len(existing_steps) + 1, command=command, target_selector=target_selector.strip() if (target_selector and target_selector.strip()) else None, input_value=final_input.strip() if (final_input and final_input.strip()) else None)
    
    db.add(new_step)
    await db.commit()
    await db.refresh(test_case)

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, "Langkah instruksi berhasil ditambahkan!")


@router.post("/testcase/{case_id}/step/{step_id}/edit")
async def update_test_step(case_id: int, step_id: int, request: Request, command: str = Form(...), target_selector: Optional[str] = Form(None), input_value: Optional[str] = Form(None), input_value_select: Optional[str] = Form(None), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    result = await db.execute(select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id))
    step = result.scalar_one_or_none()
    
    final_input = input_value_select if (command == "INCLUDE_SCENARIO" and input_value_select) else input_value
    if step:
        step.command = command
        step.target_selector = target_selector.strip() if (target_selector and target_selector.strip()) else None
        step.input_value = final_input.strip() if (final_input and final_input.strip()) else None
        await db.commit()
        await db.refresh(test_case)

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, "Langkah instruksi berhasil diperbarui!")


@router.delete("/testcase/{case_id}/step/{step_id}")
async def delete_test_step(case_id: int, step_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    
    result = await db.execute(select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id))
    step = result.scalar_one_or_none()
    
    if step:
        await db.delete(step)
        await db.commit()
        
        remaining_result = await db.execute(select(TestStep).where(TestStep.test_case_id == case_id).order_by(TestStep.step_order.asc()))
        for index, rem_step in enumerate(remaining_result.scalars().all(), start=1):
            rem_step.step_order = index
        await db.commit()

    await db.refresh(test_case, attribute_names=['steps'])
    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, "Langkah instruksi berhasil dihapus.")


@router.post("/testcase/{case_id}/step/{step_id}/move/{direction}")
async def move_step_order(case_id: int, step_id: int, direction: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    result = await db.execute(select(TestStep).where(TestStep.id == step_id, TestStep.test_case_id == case_id))
    current_step = result.scalar_one_or_none()
    if not current_step: raise HTTPException(status_code=404, detail="Step tidak ditemukan")

    current_order = current_step.step_order
    target_order = current_order - 1 if direction == "up" else current_order + 1

    neighbor_result = await db.execute(select(TestStep).where(TestStep.test_case_id == case_id, TestStep.step_order == target_order))
    neighbor_step = neighbor_result.scalar_one_or_none()

    if neighbor_step:
        current_step.step_order = target_order
        neighbor_step.step_order = current_order
        await db.commit()

    steps_result = await db.execute(select(TestStep).where(TestStep.test_case_id == case_id).order_by(TestStep.step_order.asc()))
    test_case.steps = steps_result.scalars().all()
    
    return templates.TemplateResponse("partials/step_list.html", {"request": {}, "case": test_case, "steps": test_case.steps})


@router.post("/testcase/{case_id}/run")
async def run_test(case_id: int, request: Request, background_tasks: BackgroundTasks, record_video: Optional[str] = Form(None), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await get_user_testcase_or_404(db, case_id, current_user.id) # Proteksi akses
    
    # 1. AUTO-CLEANUP: Hanya hapus video temp dari skenario milik current_user
    temp_runs_query = select(TestRun).join(TestCase).join(Project).where(TestRun.video_url.like("%temp_%"), Project.user_id == current_user.id)
    unkept_runs = (await db.execute(temp_runs_query)).scalars().all()
    for old_run in unkept_runs:
        if old_run.video_url:
            filepath = old_run.video_url.lstrip("/")
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass
            old_run.video_url = None
    await db.commit()

    should_record = True if (record_video and record_video.lower() in ["true", "on", "1"]) else False

    run_id = f"RUN-{str(uuid.uuid4())[:8].upper()}"
    new_run = TestRun(id=run_id, test_case_id=case_id, status="PENDING")
    db.add(new_run)
    await db.commit()

    background_tasks.add_task(run_test_scenario, run_id, case_id, should_record)
    return templates.TemplateResponse("partials/status.html", {"request": request, "run": new_run})


@router.get("/run-status/{run_id}")
async def get_run_status(run_id: str, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    test_run = (await db.execute(run_query)).scalar_one_or_none()
    if not test_run: raise HTTPException(status_code=404)
    return templates.TemplateResponse("partials/status.html", {"request": request, "run": test_run})


@router.post("/testrun/{run_id}/keep-video")
async def keep_test_run_video(run_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    run = (await db.execute(run_query)).scalar_one_or_none()
    
    if run and run.video_url and "temp_" in run.video_url:
        permanent_url = run.video_url.replace("temp_", "")
        old_path = run.video_url.lstrip("/")
        new_path = permanent_url.lstrip("/")
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
            run.video_url = permanent_url
            await db.commit()
    return HTMLResponse('<div class="p-2.5 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-xl border border-emerald-200">✅ Video berhasil disimpan permanen untuk laporan.</div>')


@router.delete("/testrun/{run_id}/delete-video")
async def delete_test_run_video(run_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    run = (await db.execute(run_query)).scalar_one_or_none()
    
    if run and run.video_url:
        filepath = run.video_url.lstrip("/")
        if os.path.exists(filepath):
            try: os.remove(filepath)
            except Exception: pass
        run.video_url = None
        await db.commit()
    return HTMLResponse('<div class="p-2.5 bg-slate-100 text-slate-500 text-xs italic rounded-xl border border-slate-200">🗑️ Video telah dihapus dari server.</div>')


@router.get("/testrun/{run_id}/download-video")
async def download_test_run_video(run_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    run = (await db.execute(run_query)).scalar_one_or_none()
    
    if not run or not run.video_url:
        raise HTTPException(status_code=404, detail="Data video tidak ditemukan")
    filepath = run.video_url.lstrip("/")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File video fisik tidak ditemukan di server")
    return FileResponse(filepath, media_type="video/mp4", filename=f"TestRun_{run_id}.mp4")