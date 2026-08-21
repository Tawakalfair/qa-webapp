import asyncio
import json
import uuid
import os
import sys
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks, Depends, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Import Dependency Login
from app.core.config import settings
from app.api.deps import get_db, get_current_user
from app.models.models import TestCase, TestStep, TestRun, CommandDefinition, Project, User
from app.engine.executor import _async_run_test_scenario, run_test_scenario
from app.services.export_service import generate_ut_matrix_excel

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Storage sementara status batch run per project (next plan -> DB/Redis)
BATCH_STATUS = {}

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

# Storage sementara status batch run per project
BATCH_STATUS = {}

async def _async_run_batch_scenarios(project_id: int, user_id: int, db_url: str, mode: str = "SMART"):
    """Worker asynchronous internal untuk eksekusi massal skenario."""
    engine = create_async_engine(db_url)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        query = (
            select(TestCase)
            .join(Project)
            .where(TestCase.project_id == project_id, Project.user_id == user_id)
            .options(selectinload(TestCase.runs))
            .order_by(TestCase.id.asc())
        )
        result = await db.execute(query)
        all_test_cases = result.scalars().all()
        
        target_test_cases = []
        for tc in all_test_cases:
            latest_run_status = None
            if tc.runs:
                sorted_runs = sorted(tc.runs, key=lambda r: r.id, reverse=True)
                latest_run_status = sorted_runs[0].status

            if mode == "SMART":
                if not latest_run_status or latest_run_status != "SUCCESS":
                    target_test_cases.append(tc)
            else:
                target_test_cases.append(tc)

        total = len(target_test_cases)
        
        if total == 0:
            BATCH_STATUS[project_id] = {
                "total": len(all_test_cases), 
                "completed": len(all_test_cases), 
                "status": "COMPLETED", 
                "current_name": "Semua Skenario Sudah Lulus (SUCCESS)"
            }
            await engine.dispose()
            return

        BATCH_STATUS[project_id] = {"total": total, "completed": 0, "status": "RUNNING", "current_name": ""}

        for idx, tc in enumerate(target_test_cases, start=1):
            BATCH_STATUS[project_id]["completed"] = idx - 1
            BATCH_STATUS[project_id]["current_name"] = tc.name
            
            run_id = f"RUN-{str(uuid.uuid4())[:8].upper()}"
            new_run = TestRun(id=run_id, test_case_id=tc.id, status="PENDING")
            db.add(new_run)
            await db.commit()
            
            try:
                # Eksekusi Playwright tanpa rekam video
                await _async_run_test_scenario(run_id=run_id, case_id=tc.id, record_video=False)
            except Exception as e:
                print(f"[Batch Run Error] Skenario {tc.id} gagal: {e}")

        BATCH_STATUS[project_id]["completed"] = total
        BATCH_STATUS[project_id]["status"] = "COMPLETED"
        BATCH_STATUS[project_id]["current_name"] = "Selesai"

    await engine.dispose()


def run_batch_scenarios(project_id: int, user_id: int, db_url: str, mode: str = "SMART"):
    """Worker Synchronous terisolasi yang aman dari NotImplementedError di Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(_async_run_batch_scenarios(project_id, user_id, db_url, mode))


@router.post("/projects/{project_id}/run-all")
async def run_all_scenarios(
    project_id: int,
    background_tasks: BackgroundTasks,
    mode: str = Form("SMART"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Pemicu eksekusi massal yang memanggil synchronous worker di thread terisolasi."""
    proj_result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Akses ditolak.")

    BATCH_STATUS[project_id] = {"total": 0, "completed": 0, "status": "STARTING", "current_name": "Menyiapkan..."}

    # Ubah target fungsi background task dari _async_run_batch_scenarios menjadi run_batch_scenarios
    background_tasks.add_task(run_batch_scenarios, project_id, current_user.id, settings.DATABASE_URL, mode)
    
    return HTMLResponse(f"""
        <div hx-get="/projects/{project_id}/batch-progress" hx-trigger="load, every 2s" hx-swap="outerHTML">
            <p class="text-xs text-indigo-600 font-bold animate-pulse">🚀 Memulai pengujian massal ({mode})...</p>
        </div>
    """)


@router.get("/projects/{project_id}/batch-progress")
async def get_batch_progress(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Endpoint polling status kemajuan eksekusi massal + Auto-Update kartu ringkasan via OOB Swap."""
    status_info = BATCH_STATUS.get(project_id, {"total": 0, "completed": 0, "status": "IDLE", "current_name": ""})
    
    total = status_info["total"]
    completed = status_info["completed"]
    percentage = int((completed / total) * 100) if total > 0 else 0
    
    is_finished = status_info["status"] == "COMPLETED"
    trigger_header = 'hx-trigger="every 2s"' if not is_finished else ''

    progress_html = f"""
        <div id="batch-progress-box" hx-get="/projects/{project_id}/batch-progress" {trigger_header} hx-swap="outerHTML" class="space-y-2 p-3 bg-slate-50 border border-slate-200 rounded-xl">
            <div class="flex justify-between items-center text-xs font-bold text-slate-700">
                <span>{"✅ Eksekusi Massal Selesai!" if is_finished else f"⏳ Memproses: {status_info['current_name']}"}</span>
                <span>{completed} / {total} ({percentage}%)</span>
            </div>
            <div class="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
                <div class="bg-indigo-600 h-2.5 rounded-full transition-all duration-500" style="width: {percentage}%"></div>
            </div>
            {"<p class='text-[11px] text-emerald-600 font-semibold mt-1'>✨ Seluruh pengujian selesai. Angka statistik di atas telah diperbarui!</p>" if is_finished else ""}
        </div>
    """

    # JIKA SUDAH SELESAI: Hitung ulang statistik terbaru & kirim OOB Swap ke #export-summary-cards
    if is_finished:
        query = (
            select(TestCase)
            .join(Project)
            .where(TestCase.project_id == project_id, Project.user_id == current_user.id)
            .options(selectinload(TestCase.runs))
        )
        cases_result = await db.execute(query)
        cases = cases_result.scalars().all()

        success_count = 0
        failed_count = 0
        untested_count = 0

        for tc in cases:
            if not tc.runs:
                untested_count += 1
            else:
                latest_run = sorted(tc.runs, key=lambda r: r.id, reverse=True)[0]
                if latest_run.status == "SUCCESS":
                    success_count += 1
                elif latest_run.status == "FAILED":
                    failed_count += 1
                else:
                    untested_count += 1

        oob_summary_html = f"""
        <div id="export-summary-cards" hx-swap-oob="true" class="grid grid-cols-3 gap-2 py-2">
            <div class="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-center">
                <p class="text-[10px] font-bold text-emerald-600 uppercase">Lulus (PASS)</p>
                <p class="text-lg font-black text-emerald-700">{success_count}</p>
            </div>
            <div class="p-3 bg-rose-50 border border-rose-200 rounded-xl text-center">
                <p class="text-[10px] font-bold text-rose-600 uppercase">Gagal (FAIL)</p>
                <p class="text-lg font-black text-rose-700">{failed_count}</p>
            </div>
            <div class="p-3 bg-slate-100 border border-slate-200 rounded-xl text-center">
                <p class="text-[10px] font-bold text-slate-500 uppercase">Belum Dites</p>
                <p class="text-lg font-black text-slate-700">{untested_count}</p>
            </div>
        </div>
        """
        return HTMLResponse(progress_html + oob_summary_html)

    return HTMLResponse(progress_html)


# ==========================================
# RUTE DASHBOARD & FILTER SKENARIO
# ==========================================

@router.get("/")
async def dashboard(
    request: Request,
    project_id: Optional[str] = Query(None),
    test_type: Optional[str] = Query(None),
    selected_id: Optional[str] = Query(None),  # 🟢 Read selected_id query param
    msg: Optional[str] = Query(None),
    type: Optional[str] = Query("success"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render main workspace dashboard and automatically load selected scenario if selected_id is provided."""
    parsed_project_id: Optional[int] = int(project_id.strip()) if (project_id and project_id.strip().isdigit()) else None
    parsed_selected_id: Optional[int] = int(selected_id.strip()) if (selected_id and selected_id.strip().isdigit()) else None

    # Fetch user projects for header filter
    proj_result = await db.execute(
        select(Project).where(Project.user_id == current_user.id).order_by(Project.name.asc())
    )
    projects = proj_result.scalars().all()

    # Query test cases for left sidebar
    query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(selectinload(TestCase.project), selectinload(TestCase.runs))
        .order_by(TestCase.id.desc())
    )

    if parsed_project_id:
        query = query.where(TestCase.project_id == parsed_project_id)
    if test_type and test_type.strip():
        query = query.where(TestCase.test_type == test_type.strip())

    cases_result = await db.execute(query)
    test_cases = cases_result.scalars().all()

    # 🟢 If selected_id is provided, eager load that scenario for the right workspace panel
    selected_case = None
    commands = []
    other_cases = []

    if parsed_selected_id:
        selected_case_query = (
            select(TestCase)
            .join(Project)
            .where(TestCase.id == parsed_selected_id, Project.user_id == current_user.id)
            .options(
                selectinload(TestCase.project),
                selectinload(TestCase.steps),
                selectinload(TestCase.runs)  # Prevents MissingGreenlet error
            )
        )
        selected_case_res = await db.execute(selected_case_query)
        selected_case = selected_case_res.scalar_one_or_none()

        if selected_case:
            # Sync selected_project_id if it wasn't provided in the URL
            if not parsed_project_id:
                parsed_project_id = selected_case.project_id

            cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
            commands = cmd_result.scalars().all()

            other_cases_result = await db.execute(
                select(TestCase)
                .join(Project)
                .where(TestCase.id != selected_case.id, Project.user_id == current_user.id)
                .options(selectinload(TestCase.project))
                .order_by(TestCase.name.asc())
            )
            other_cases = other_cases_result.scalars().all()

    response = templates.TemplateResponse("index.html", {
        "request": request,
        "title": "QA Automata - Workspace",
        "projects": projects,
        "test_cases": test_cases,
        "selected_project_id": parsed_project_id,
        "selected_test_type": test_type or "",
        "selected_case_id": parsed_selected_id,
        "case": selected_case,  # Passed directly for right_panel.html
        "commands": commands,
        "other_cases": other_cases,
        "current_user": current_user
    })

    if msg:
        return trigger_toast(response, msg, type)
    return response


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
# CREATE SCENARIO MODAL ROUTE
# ==========================================

@router.get("/testcase/new-modal")
async def get_create_case_modal(
    request: Request,
    project_id: Optional[str] = Query(None), # 🟢 Read active project filter
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render modal dialog for creating a new test scenario with active project pre-selected."""
    parsed_project_id: Optional[int] = int(project_id.strip()) if (project_id and project_id.strip().isdigit()) else None

    proj_result = await db.execute(
        select(Project).where(Project.user_id == current_user.id).order_by(Project.name.asc())
    )
    projects = proj_result.scalars().all()
    
    return templates.TemplateResponse("partials/create_case_modal.html", {
        "request": request,
        "projects": projects,
        "selected_project_id": parsed_project_id # 🟢 Pass selected project ID to template
    })


# ==========================================
# FETCH SCENARIO WORKSPACE PANEL
# ==========================================

@router.get("/testcase/{case_id}")
async def get_test_case_panel(
    case_id: int, 
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Fetch test case details and render the right panel workspace with eager-loaded steps and runs."""
    # 🟢 Set eager_load_runs=True to prevent MissingGreenlet error in right_panel.html
    test_case = await get_user_testcase_or_404(
        db, case_id, current_user.id, eager_load_steps=True, eager_load_runs=True
    )
    
    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    all_cases_result = await db.execute(
        select(TestCase)
        .join(Project)
        .where(TestCase.id != case_id, Project.user_id == current_user.id)
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
    base_url: Optional[str] = Form(None),  # Made optional
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
    """Create a new test scenario with optional base_url and redirect to dashboard."""
    if not project_id or not project_id.strip().isdigit():
        msg = "Invalid target project."
        return RedirectResponse(url=f"/?msg={msg}&type=error", status_code=303)

    parsed_project_id = int(project_id.strip())

    proj_result = await db.execute(
        select(Project).where(Project.id == parsed_project_id, Project.user_id == current_user.id)
    )
    if not proj_result.scalar_one_or_none():
        return RedirectResponse(url=f"/?msg=Access denied&type=error", status_code=303)

    # Sanitize base_url
    clean_base_url = base_url.strip() if (base_url and base_url.strip()) else None

    new_case = TestCase(
        project_id=parsed_project_id,
        name=name.strip(),
        base_url=clean_base_url,
        test_type=test_type,
        reference_number=reference_number.strip() if (reference_number and reference_number.strip()) else None,
        ut_theme=ut_theme.strip() if (ut_theme and ut_theme.strip()) else None,
        ut_function_name=ut_function_name.strip() if (ut_function_name and ut_function_name.strip()) else None,
        ut_action=ut_action.strip() if (ut_action and ut_action.strip()) else None,
        ut_condition_1=ut_condition_1.strip() if (ut_condition_1 and ut_condition_1.strip()) else clean_base_url,
        ut_condition_2=ut_condition_2.strip() if (ut_condition_2 and ut_condition_2.strip()) else None,
        ut_classification=ut_classification.strip() if (ut_classification and ut_classification.strip()) else None,
        ut_how_to_test=ut_how_to_test.strip() if (ut_how_to_test and ut_how_to_test.strip()) else None,
        ut_expected_results=ut_expected_results.strip() if (ut_expected_results and ut_expected_results.strip()) else None
    )
    db.add(new_case)
    await db.commit()
    
    msg = f"Scenario '{new_case.name}' successfully created!"
    return RedirectResponse(url=f"/?project_id={parsed_project_id}&selected_id={new_case.id}&msg={msg}&type=success", status_code=303)

@router.get("/testcase/{case_id}/edit-modal")
async def get_edit_case_modal(
    case_id: int, 
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    return templates.TemplateResponse("partials/edit_case_modal.html", {"request": request, "case": test_case})


@router.post("/testcase/{case_id}/edit")
async def update_test_case(
    case_id: int,
    request: Request,
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

    # OOB Swap All Cases List agar sidebar ikut terbarui secara instan
    all_cases_query = select(TestCase).join(Project).where(Project.user_id == current_user.id).options(selectinload(TestCase.project)).order_by(TestCase.id.asc())
    if test_case.project_id:
        all_cases_query = all_cases_query.where(TestCase.project_id == test_case.project_id)
    all_cases_result = await db.execute(all_cases_query)
    all_test_cases = all_cases_result.scalars().all()

    response_html = f"""
    {templates.get_template("partials/right_panel.html").render({
        "request": request,
        "case": test_case,
        "commands": commands,
        "other_cases": other_cases
    })}
    <div id="case-list-container" hx-swap-oob="true">
        {templates.get_template("partials/case_list.html").render({"request": request, "test_cases": all_test_cases, "selected_case_id": test_case.id})}
    </div>
    <div id="modal-container" hx-swap-oob="true"></div>
    """
    
    return trigger_toast(HTMLResponse(response_html), f"Skenario '{test_case.name}' berhasil diperbarui!")


@router.get("/testcases/list-partial")
async def get_case_list_partial(
    request: Request,
    project_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    parsed_project_id = int(project_id.strip()) if project_id and project_id.strip().isdigit() else None
    
    query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(selectinload(TestCase.project))
    )
    
    if parsed_project_id:
        query = query.where(TestCase.project_id == parsed_project_id)
        
    if q and q.strip():
        query = query.where(TestCase.name.ilike(f"%{q.strip()}%"))
        
    query = query.order_by(TestCase.id.asc())
    result = await db.execute(query)
    test_cases = result.scalars().all()
    
    return templates.TemplateResponse("partials/case_list.html", {
        "request": request,
        "test_cases": test_cases,
        "selected_case_id": None
    })


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
    """Update scenario UT Metadata and re-render workspace panel."""
    # 🟢 Set eager_load_runs=True here as well
    test_case = await get_user_testcase_or_404(
        db, case_id, current_user.id, eager_load_steps=True, eager_load_runs=True
    )
    
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
        select(TestCase)
        .join(Project)
        .where(TestCase.id != case_id, Project.user_id == current_user.id)
        .options(selectinload(TestCase.project))
        .order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()

    res = templates.TemplateResponse("partials/right_panel.html", {
        "request": request, "case": test_case, "commands": commands, "other_cases": other_cases
    })
    return trigger_toast(res, "UT Document metadata updated successfully!")


@router.post("/testcase/{case_id}/delete")
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    name = test_case.name
    await db.delete(test_case)
    await db.commit()
    msg = f"Skenario '{name}' berhasil dihapus."
    return RedirectResponse(url=f"/?msg={msg}&type=success", status_code=303)

@router.post("/testcase/{case_id}/steps/bulk-delete")
async def bulk_delete_test_steps(
    case_id: int,
    request: Request,
    step_ids: List[int] = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete multiple test steps at once and re-index step numbers."""
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    if not step_ids:
        res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
        return trigger_toast(res, "Pilih minimal satu langkah untuk dihapus.", "error")

    # 1. delete selected steps from the database
    delete_query = select(TestStep).where(TestStep.id.in_(step_ids), TestStep.test_case_id == case_id)
    steps_to_del = (await db.execute(delete_query)).scalars().all()
    deleted_count = len(steps_to_del)

    for step_obj in steps_to_del:
        await db.delete(step_obj)
    await db.commit()

    # 2. Reorder remaining steps to maintain sequential step_order
    remaining_query = (
        select(TestStep)
        .where(TestStep.test_case_id == case_id)
        .order_by(TestStep.step_order.asc(), TestStep.id.asc())
    )
    remaining_steps = (await db.execute(remaining_query)).scalars().all()

    for idx, step_obj in enumerate(remaining_steps, start=1):
        step_obj.step_order = idx
    await db.commit()

    # 3. Refresh the test_case object to reflect updated steps
    await db.refresh(test_case, attribute_names=['steps'])

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, f"Berhasil menghapus {deleted_count} langkah!")


# ==========================================
# RUTE STEP EDITOR & EKSEKUSI
# ==========================================

@router.get("/testcase/{case_id}/step/{step_id}/edit")
async def get_edit_step_form(case_id: int, step_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await get_user_testcase_or_404(db, case_id, current_user.id)
    
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
async def add_test_step(
    case_id: int, 
    request: Request, 
    command: str = Form(...), 
    target_selector: Optional[str] = Form(None), 
    input_value: Optional[str] = Form(None), 
    input_value_select: Optional[str] = Form(None),
    target_step_order: Optional[str] = Form(None),  # 🟢 Parameter nomor urutan posisi langkah
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    
    # 🟢 1. Ambil langkah-langkah yang ada dan urutkan
    existing_steps = sorted(test_case.steps, key=lambda s: s.step_order) if test_case.steps else []
    total_steps = len(existing_steps)

    parsed_order = int(target_step_order.strip()) if (target_step_order and target_step_order.strip().isdigit()) else None

    # 🟢 2. Logika pergeseran urutan jika disisipkan di posisi tertentu
    if parsed_order and 1 <= parsed_order <= total_steps:
        for s in existing_steps:
            if s.step_order >= parsed_order:
                s.step_order += 1
        new_step_order = parsed_order
    else:
        new_step_order = total_steps + 1

    final_input = input_value_select if (command == "INCLUDE_SCENARIO" and input_value_select) else input_value
    new_step = TestStep(
        test_case_id=case_id, 
        step_order=new_step_order, 
        command=command, 
        target_selector=target_selector.strip() if (target_selector and target_selector.strip()) else None, 
        input_value=final_input.strip() if (final_input and final_input.strip()) else None
    )
    
    db.add(new_step)
    await db.commit()
    await db.refresh(test_case, attribute_names=['steps'])

    res = templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case})
    return trigger_toast(res, f"Langkah instruksi berhasil ditambahkan di posisi #{new_step_order}!")


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
async def move_step_order(
    case_id: int, 
    step_id: int, 
    direction: str, 
    request: Request,
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
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
    
    return templates.TemplateResponse("partials/step_list.html", {"request": request, "case": test_case, "steps": test_case.steps})


@router.post("/testcase/{case_id}/run")
async def run_test(
    case_id: int, 
    request: Request, 
    record_video: Optional[str] = Form(None), 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Jalankan tes secara langsung tanpa polling dan kembalikan hasil akhirnya."""
    await get_user_testcase_or_404(db, case_id, current_user.id)

    # 1. Bersihkan video temp lama milik user ini
    temp_runs_query = (
        select(TestRun)
        .join(TestCase)
        .join(Project)
        .where(TestRun.video_url.like("%temp_%"), Project.user_id == current_user.id)
    )
    unkept_runs = (await db.execute(temp_runs_query)).scalars().all()
    user_video_dir = os.path.join("static", "videos", f"user_{current_user.id}")
    for old_run in unkept_runs:
        if old_run.video_url:
            filename = old_run.video_url.split("/")[-1]
            filepath = os.path.join(user_video_dir, filename)
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass
            old_run.video_url = None
    await db.commit()

    should_record = True if (record_video and record_video.lower() in ["true", "on", "1"]) else False
    run_id = f"RUN-{str(uuid.uuid4())[:8].upper()}"

    # 2. Buat entri TestRun awal
    new_run = TestRun(id=run_id, test_case_id=case_id, status="PENDING")
    db.add(new_run)
    await db.commit()

    # 3. 🟢 LANGSUNG TUNGGU (AWAIT) PLAYWRIGHT SELESAI (Tanpa BackgroundTasks)
    await _async_run_test_scenario(
        run_id=run_id, 
        case_id=case_id, 
        record_video=should_record, 
        user_id=current_user.id
    )

    # 4. Ambil hasil akhir dari database
    result_run = await db.execute(select(TestRun).where(TestRun.id == run_id))
    completed_run = result_run.scalar_one()

    # 5. Langsung kembalikan tampilan hasil akhir ke UI
    return templates.TemplateResponse("partials/status.html", {
        "request": request, 
        "run": completed_run
    })


@router.get("/stream-video/{user_id}/{filename}")
async def stream_video(
    user_id: int, 
    filename: str, 
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Stream user-isolated video file with Byte-Range HTTP 206 support."""
    # 🟢 Prevent cross-user unauthorized video playback
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this media file.")

    video_path = os.path.join("static", "videos", f"user_{user_id}", filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found.")

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("range")

    if range_header:
        bytes_type, bytes_range = range_header.split("=")
        start_str, end_str = bytes_range.split("-")
        
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        chunk_size = (end - start) + 1

        def video_chunk_generator():
            with open(video_path, "rb") as video_file:
                video_file.seek(start)
                yield video_file.read(chunk_size)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(video_chunk_generator(), status_code=206, headers=headers)

    return FileResponse(video_path, media_type="video/mp4")

@router.get("/run-status/{run_id}")
async def get_run_status(
    run_id: str, 
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Fetch run execution status with optimized OOB Swap table update upon completion."""
    run_query = (
        select(TestRun)
        .join(TestCase)
        .join(Project)
        .where(TestRun.id == run_id, Project.user_id == current_user.id)
    )
    test_run = (await db.execute(run_query)).scalar_one_or_none()
    
    if not test_run: 
        raise HTTPException(status_code=404, detail="Run status not found.")

    status_html = templates.get_template("partials/status.html").render({"request": request, "run": test_run})

    # 🟢 OPTIMIZED: Update table only when finished, loading ONLY recent runs
    if test_run.status in ["SUCCESS", "FAILED"]:
        # Subquery or query optimization: eager load runs with limit/sorting
        updated_query = (
            select(TestCase)
            .join(Project)
            .where(Project.user_id == current_user.id)
            .options(
                selectinload(TestCase.project), 
                selectinload(TestCase.steps),
                # ⚡ Load only necessary runs data without pulling massive history
                selectinload(TestCase.runs)
            )
            .order_by(TestCase.id.desc())
        )
        test_cases = (await db.execute(updated_query)).scalars().all()

        table_html = templates.get_template("partials/scenario_table.html").render({
            "request": request, 
            "test_cases": test_cases
        })

        oob_table_html = f'<div id="scenario-table-container" hx-swap-oob="true">{table_html}</div>'
        return HTMLResponse(status_html + oob_table_html)

    return HTMLResponse(status_html)


@router.post("/testrun/{run_id}/keep-video")
async def keep_test_run_video(
    run_id: str, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    run = (await db.execute(run_query)).scalar_one_or_none()
    
    if run and run.video_url and "temp_" in run.video_url:
        permanent_url = run.video_url.replace("temp_", "")
        old_filename = run.video_url.split("/")[-1]
        new_filename = permanent_url.split("/")[-1]
        
        user_video_dir = os.path.join("static", "videos", f"user_{current_user.id}")
        old_path = os.path.join(user_video_dir, old_filename)
        new_path = os.path.join(user_video_dir, new_filename)

        if os.path.exists(old_path):
            os.rename(old_path, new_path)
            run.video_url = permanent_url
            await db.commit()
            
    return HTMLResponse('<div class="p-2.5 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-xl border border-emerald-200">✅ Video permanently saved.</div>')


@router.delete("/testrun/{run_id}/delete-video")
async def delete_test_run_video(
    run_id: str, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    run = (await db.execute(run_query)).scalar_one_or_none()
    
    if run and run.video_url:
        filename = run.video_url.split("/")[-1]
        filepath = os.path.join("static", "videos", f"user_{current_user.id}", filename)
        if os.path.exists(filepath):
            try: 
                os.remove(filepath)
            except Exception: 
                pass
        run.video_url = None
        await db.commit()
        
    return HTMLResponse('<div class="p-2.5 bg-slate-100 text-slate-500 text-xs italic rounded-xl border border-slate-200">🗑️ Video deleted from server.</div>')


@router.get("/testrun/{run_id}/download-video")
async def download_test_run_video(run_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    run_query = select(TestRun).join(TestCase).join(Project).where(TestRun.id == run_id, Project.user_id == current_user.id)
    run = (await db.execute(run_query)).scalar_one_or_none()
    
    if not run or not run.video_url:
        raise HTTPException(status_code=404, detail="Data video tidak ditemukan")
        
    filename = run.video_url.split("/")[-1]
    filepath = os.path.join("static", "videos", filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File video fisik tidak ditemukan di server")
        
    return FileResponse(filepath, media_type="video/mp4", filename=f"TestRun_{run_id}.mp4")

# ==========================================
# RUTE IMPOR LANGKAH SKENARIO (COPY STEPS)
# ==========================================

@router.get("/testcase/{case_id}/import-modal")
async def get_import_steps_modal(case_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    target_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    
    all_cases_result = await db.execute(
        select(TestCase).join(Project).where(TestCase.id != case_id, Project.user_id == current_user.id)
        .options(selectinload(TestCase.project)).order_by(TestCase.name.asc())
    )
    other_cases = all_cases_result.scalars().all()
    
    return templates.TemplateResponse("partials/import_steps_modal.html", {
        "request": request, "case": target_case, "other_cases": other_cases
    })


@router.post("/testcase/{case_id}/import-steps")
async def import_steps_from_scenario(
    case_id: int,
    request: Request,
    source_case_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    target_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    source_case = await get_user_testcase_or_404(db, source_case_id, current_user.id, eager_load_steps=True)

    if not source_case.steps:
        error_html = f"""
        {templates.get_template("partials/step_list.html").render({"request": request, "case": target_case})}
        <div id="modal-container" hx-swap-oob="true"></div>
        """
        return trigger_toast(HTMLResponse(error_html), "Skenario sumber tidak memiliki langkah apapun untuk disalin.", "error")

    current_step_count = len(target_case.steps)
    sorted_source_steps = sorted(source_case.steps, key=lambda s: s.step_order)

    for idx, source_step in enumerate(sorted_source_steps, start=1):
        new_step = TestStep(
            test_case_id=case_id,
            step_order=current_step_count + idx,
            command=source_step.command,
            target_selector=source_step.target_selector,
            input_value=source_step.input_value
        )
        db.add(new_step)

    await db.commit()
    await db.refresh(target_case, attribute_names=['steps'])

    success_html = f"""
    <div id="step-list-container" hx-swap-oob="true">
        {templates.get_template("partials/step_list.html").render({"request": request, "case": target_case})}
    </div>
    <div id="modal-container" hx-swap-oob="true"></div>
    """
    return trigger_toast(HTMLResponse(success_html), f"{len(source_case.steps)} langkah berhasil diimpor!")


# ==========================================
# RUTE DUPLIKAT/COPY SKENARIO UTUH (CLONE)
# ==========================================

@router.get("/testcase/{case_id}/copy-modal")
async def get_copy_case_modal(
    case_id: int, 
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    test_case = await get_user_testcase_or_404(db, case_id, current_user.id)
    
    projects_result = await db.execute(
        select(Project).where(Project.user_id == current_user.id).order_by(Project.name.asc())
    )
    projects = projects_result.scalars().all()
    
    return templates.TemplateResponse("partials/copy_case_modal.html", {
        "request": request, 
        "case": test_case,
        "projects": projects,
        "suggested_name": f"Copy of {test_case.name}"
    })


@router.post("/testcase/{case_id}/copy")
async def copy_test_case(
    case_id: int,
    request: Request,
    new_name: str = Form(...),
    target_project_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Memproses penggandaan skenario utuh beserta seluruh langkah dan metadata UT Document."""
    source_case = await get_user_testcase_or_404(db, case_id, current_user.id, eager_load_steps=True)
    project_id = target_project_id if target_project_id else source_case.project_id

    # 1. Buat objek TestCase baru dengan menyalin SELURUH metadata UT Document
    new_case = TestCase(
        name=new_name.strip(),
        base_url=source_case.base_url,
        test_type=source_case.test_type,
        reference_number=source_case.reference_number,
        # 🟢 Menyalin 8 Kolom Metadata UT Document secara lengkap
        ut_theme=source_case.ut_theme,
        ut_function_name=source_case.ut_function_name,
        ut_action=source_case.ut_action,
        ut_condition_1=source_case.ut_condition_1,
        ut_condition_2=source_case.ut_condition_2,
        ut_classification=source_case.ut_classification,
        ut_how_to_test=source_case.ut_how_to_test,
        ut_expected_results=source_case.ut_expected_results,
        project_id=project_id
    )
    db.add(new_case)
    await db.flush()

    # 2. Salin seluruh TestStep secara berurutan
    if source_case.steps:
        sorted_steps = sorted(source_case.steps, key=lambda s: s.step_order)
        for step in sorted_steps:
            cloned_step = TestStep(
                test_case_id=new_case.id,
                step_order=step.step_order,
                command=step.command,
                target_selector=step.target_selector,
                input_value=step.input_value
            )
            db.add(cloned_step)

    await db.commit()

    refreshed_case_result = await db.execute(
        select(TestCase)
        .where(TestCase.id == new_case.id)
        .options(selectinload(TestCase.project), selectinload(TestCase.steps), selectinload(TestCase.runs))
    )
    copied_case = refreshed_case_result.scalar_one()

    cmd_result = await db.execute(select(CommandDefinition).order_by(CommandDefinition.code.asc()))
    commands = cmd_result.scalars().all()

    other_cases_result = await db.execute(
        select(TestCase).where(TestCase.id != copied_case.id, TestCase.project_id == project_id)
        .options(selectinload(TestCase.project)).order_by(TestCase.name.asc())
    )
    other_cases = other_cases_result.scalars().all()

    all_cases_result = await db.execute(
        select(TestCase).where(TestCase.project_id == project_id)
        .options(selectinload(TestCase.project)).order_by(TestCase.id.asc())
    )
    all_test_cases = all_cases_result.scalars().all()

    response_html = f"""
    {templates.get_template("partials/right_panel.html").render({
        "request": request,
        "case": copied_case,
        "commands": commands,
        "other_cases": other_cases
    })}
    <div id="case-list-container" hx-swap-oob="true">
        {templates.get_template("partials/case_list.html").render({"request": request, "test_cases": all_test_cases, "selected_case_id": copied_case.id})}
    </div>
    <div id="modal-container" hx-swap-oob="true"></div>
    """
    
    return trigger_toast(HTMLResponse(response_html), f"Skenario '{copied_case.name}' berhasil diduplikat beserta metadata UT!")


@router.get("/stream-video/{filename}")
async def stream_video(filename: str, request: Request):
    video_path = os.path.join("static", "videos", filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video tidak ditemukan")

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("range")

    if range_header:
        bytes_type, bytes_range = range_header.split("=")
        start_str, end_str = bytes_range.split("-")
        
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        chunk_size = (end - start) + 1

        def video_chunk_generator():
            with open(video_path, "rb") as video_file:
                video_file.seek(start)
                yield video_file.read(chunk_size)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(video_chunk_generator(), status_code=206, headers=headers)

    return FileResponse(video_path, media_type="video/mp4")