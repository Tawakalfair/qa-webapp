import os
import sys
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional
import urllib.parse

from fastapi import APIRouter, Depends, Query, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.deps import get_db, get_current_user
from app.api.v1.dashboard import trigger_toast
from app.core.config import settings
from app.engine.executor import _async_run_test_scenario
from app.models.models import CommandDefinition, TestCase, TestRun, TestStep, Project, User

router = APIRouter(prefix="/scenarios", tags=["Scenario Management"])
templates = Jinja2Templates(directory="templates")

# 🟢 Global tracker for bulk execution progress
BATCH_STATUS = {}


# =========================================================================
# BACKGROUND WORKER (EXECUTE SELECTED SCENARIOS)
# =========================================================================
async def _async_run_selected_scenarios(case_ids: List[int], user_id: int, db_url: str, batch_id: str):
    """Background worker to execute selected scenarios sequentially."""
    engine = create_async_engine(db_url)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        query = (
            select(TestCase)
            .join(Project)
            .where(TestCase.id.in_(case_ids), Project.user_id == user_id)
            .order_by(TestCase.id.asc())
        )
        result = await db.execute(query)
        test_cases = result.scalars().all()
        total = len(test_cases)

        if batch_id in BATCH_STATUS:
            BATCH_STATUS[batch_id]["total"] = total
            BATCH_STATUS[batch_id]["completed"] = 0
            BATCH_STATUS[batch_id]["status"] = "RUNNING"
            BATCH_STATUS[batch_id]["current_name"] = ""

        for idx, tc in enumerate(test_cases, start=1):
            if batch_id in BATCH_STATUS:
                BATCH_STATUS[batch_id]["completed"] = idx - 1
                BATCH_STATUS[batch_id]["current_name"] = tc.name

            run_id = f"RUN-{str(uuid.uuid4())[:8].upper()}"
            
            new_run = TestRun(
                id=run_id, 
                test_case_id=tc.id, 
                status="PENDING",
                executed_at=datetime.utcnow()
            )
            db.add(new_run)
            await db.commit()

            try:
                await _async_run_test_scenario(
                    run_id=run_id, 
                    case_id=tc.id, 
                    record_video=False, 
                    user_id=user_id
                )
            except Exception as e:
                print(f"[Bulk Run Error] Scenario {tc.id} failed: {e}")

            await asyncio.sleep(1.0)

        if batch_id in BATCH_STATUS:
            BATCH_STATUS[batch_id]["completed"] = total
            BATCH_STATUS[batch_id]["status"] = "COMPLETED"
            BATCH_STATUS[batch_id]["current_name"] = "All Done"
            
        await engine.dispose()


def run_selected_scenarios(case_ids: List[int], user_id: int, db_url: str, batch_id: str):
    """Isolated synchronous worker thread safe for Windows Proactor Event Loop."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(_async_run_selected_scenarios(case_ids, user_id, db_url, batch_id))


# =========================================================================
# 1. SCENARIO INVENTORY & FILTERING ROUTES
# =========================================================================
@router.get("")
async def render_scenario_inventory(
    request: Request,
    project_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render the full Scenario Inventory page."""
    parsed_project_id: Optional[int] = None
    if project_id and project_id.strip().isdigit():
        parsed_project_id = int(project_id.strip())

    proj_query = select(Project).where(Project.user_id == current_user.id).order_by(Project.name.asc())
    projects = (await db.execute(proj_query)).scalars().all()

    query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
        .order_by(TestCase.id.desc())
    )

    if parsed_project_id:
        query = query.where(TestCase.project_id == parsed_project_id)
    if q and q.strip():
        query = query.where(TestCase.name.ilike(f"%{q.strip()}%"))

    test_cases = (await db.execute(query)).scalars().all()

    return templates.TemplateResponse("scenarios.html", {
        "request": request,
        "test_cases": test_cases,
        "projects": projects,
        "selected_project_id": parsed_project_id,
        "search_query": q or "",
        "current_user": current_user
    })


@router.get("/table-partial")
async def render_scenario_table_partial(
    request: Request,
    project_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render filtered scenario table fragment for HTMX requests."""
    parsed_project_id: Optional[int] = None
    if project_id and project_id.strip().isdigit():
        parsed_project_id = int(project_id.strip())

    query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
        .order_by(TestCase.id.desc())
    )

    if parsed_project_id:
        query = query.where(TestCase.project_id == parsed_project_id)
    if q and q.strip():
        query = query.where(TestCase.name.ilike(f"%{q.strip()}%"))

    test_cases = (await db.execute(query)).scalars().all()

    return templates.TemplateResponse("partials/scenario_table.html", {
        "request": request,
        "test_cases": test_cases
    })


# =========================================================================
# 2. DETAIL MODAL & METADATA EDIT ROUTES
# =========================================================================
@router.get("/{case_id}/detail-modal")
async def render_scenario_detail_modal(
    case_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render scenario detail modal dialog."""
    query = (
        select(TestCase)
        .join(Project)
        .where(TestCase.id == case_id, Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
    )
    case_obj = (await db.execute(query)).scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    return templates.TemplateResponse("partials/scenario_detail_modal.html", {
        "request": request,
        "case": case_obj
    })


@router.post("/{case_id}/edit-modal-save")
async def save_scenario_detail_modal(
    case_id: int,
    request: Request,
    name: str = Form(...),
    base_url: Optional[str] = Form(None),
    test_type: str = Form("REGRESSION"),
    reference_number: Optional[str] = Form(None),
    ut_theme: Optional[str] = Form(None),
    ut_function_name: Optional[str] = Form(None),
    ut_classification: Optional[str] = Form(None),
    ut_condition_1: Optional[str] = Form(None),
    ut_condition_2: Optional[str] = Form(None),
    ut_action: Optional[str] = Form(None),
    ut_how_to_test: Optional[str] = Form(None),
    ut_expected_results: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    q: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save scenario info and UT metadata from detail modal and refresh table respecting active filters."""
    case_query = select(TestCase).join(Project).where(TestCase.id == case_id, Project.user_id == current_user.id)
    case_obj = (await db.execute(case_query)).scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    case_obj.name = name.strip()
    case_obj.base_url = base_url.strip() if base_url else ""
    case_obj.test_type = test_type
    case_obj.reference_number = reference_number.strip() if reference_number else None
    case_obj.ut_theme = ut_theme.strip() if ut_theme else None
    case_obj.ut_function_name = ut_function_name.strip() if ut_function_name else None
    case_obj.ut_classification = ut_classification.strip() if ut_classification else None
    case_obj.ut_condition_1 = ut_condition_1.strip() if ut_condition_1 else None
    case_obj.ut_condition_2 = ut_condition_2.strip() if ut_condition_2 else None
    case_obj.ut_action = ut_action.strip() if ut_action else None
    case_obj.ut_how_to_test = ut_how_to_test.strip() if ut_how_to_test else None
    case_obj.ut_expected_results = ut_expected_results.strip() if ut_expected_results else None

    await db.commit()

    parsed_project_id = int(project_id.strip()) if (project_id and project_id.strip().isdigit()) else None
    updated_query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
        .order_by(TestCase.id.desc())
    )
    if parsed_project_id:
        updated_query = updated_query.where(TestCase.project_id == parsed_project_id)
    if q and q.strip():
        updated_query = updated_query.where(TestCase.name.ilike(f"%{q.strip()}%"))

    test_cases = (await db.execute(updated_query)).scalars().all()
    response_html = f"""
    <div id="scenario-table-container" hx-swap-oob="true" class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {templates.get_template("partials/scenario_table.html").render({"request": request, "test_cases": test_cases})}
    </div>
    """
    return trigger_toast(HTMLResponse(response_html), f"Scenario '{case_obj.name}' successfully updated!")


# =========================================================================
# 3. BATCH DUPLICATE & BATCH DELETE ROUTES
# =========================================================================
@router.post("/bulk-copy-modal")
async def render_bulk_copy_modal(
    request: Request,
    case_ids: List[int] = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render batch duplication setup modal."""
    if not case_ids:
        return trigger_toast(HTMLResponse(""), "Pilih minimal 1 skenario.", "warning")

    cases_query = (
        select(TestCase)
        .join(Project)
        .where(TestCase.id.in_(case_ids), Project.user_id == current_user.id)
        .options(selectinload(TestCase.project))
    )
    cases = (await db.execute(cases_query)).scalars().all()

    proj_query = select(Project).where(Project.user_id == current_user.id).order_by(Project.name.asc())
    projects = (await db.execute(proj_query)).scalars().all()

    return templates.TemplateResponse("partials/bulk_copy_modal.html", {
        "request": request,
        "selected_cases": cases,
        "projects": projects
    })


@router.post("/bulk-copy")
async def process_bulk_copy(
    request: Request,
    case_ids: List[int] = Form(...),
    new_names: List[str] = Form(...),
    target_project_id: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    q: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Process duplicate for multiple scenarios at once and refresh table respecting active filters."""
    if len(case_ids) != len(new_names):
        return trigger_toast(HTMLResponse("Mismatched scenarios and names count."), "Mismatched parameters.", "error")

    copied_count = 0
    for case_id, new_name in zip(case_ids, new_names):
        query = (
            select(TestCase)
            .join(Project)
            .where(TestCase.id == case_id, Project.user_id == current_user.id)
            .options(selectinload(TestCase.steps))
        )
        source_case = (await db.execute(query)).scalar_one_or_none()
        if not source_case:
            continue

        proj_id = int(target_project_id) if (target_project_id and target_project_id.strip().isdigit()) else source_case.project_id

        cloned_case = TestCase(
            name=new_name.strip(),
            base_url=source_case.base_url,
            test_type=source_case.test_type,
            reference_number=source_case.reference_number,
            ut_theme=source_case.ut_theme,
            ut_function_name=source_case.ut_function_name,
            ut_action=source_case.ut_action,
            ut_condition_1=source_case.ut_condition_1,
            ut_condition_2=source_case.ut_condition_2,
            ut_classification=source_case.ut_classification,
            ut_how_to_test=source_case.ut_how_to_test,
            ut_expected_results=source_case.ut_expected_results,
            project_id=proj_id
        )
        db.add(cloned_case)
        await db.flush()

        if source_case.steps:
            sorted_steps = sorted(source_case.steps, key=lambda s: s.step_order)
            for step in sorted_steps:
                db.add(TestStep(
                    test_case_id=cloned_case.id,
                    step_order=step.step_order,
                    command=step.command,
                    target_selector=step.target_selector,
                    input_value=step.input_value
                ))
        copied_count += 1

    await db.commit()

    parsed_project_id = int(project_id.strip()) if (project_id and project_id.strip().isdigit()) else None
    updated_query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
        .order_by(TestCase.id.desc())
    )
    if parsed_project_id:
        updated_query = updated_query.where(TestCase.project_id == parsed_project_id)
    if q and q.strip():
        updated_query = updated_query.where(TestCase.name.ilike(f"%{q.strip()}%"))

    test_cases = (await db.execute(updated_query)).scalars().all()
    response_html = f"""
    <div id="scenario-table-container" hx-swap-oob="true" class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {templates.get_template("partials/scenario_table.html").render({"request": request, "test_cases": test_cases})}
    </div>
    <div id="modal-container" hx-swap-oob="true"></div>
    """
    return trigger_toast(HTMLResponse(response_html), f"Successfully duplicated {copied_count} scenario(s)!")


@router.post("/bulk-delete")
async def process_bulk_delete(
    request: Request,
    case_ids: List[int] = Form(...),
    project_id: Optional[str] = Form(None),
    q: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete multiple selected scenarios at once."""
    if not case_ids:
        return trigger_toast(HTMLResponse(""), "Pilih minimal 1 skenario.", "warning")

    query = select(TestCase).join(Project).where(TestCase.id.in_(case_ids), Project.user_id == current_user.id)
    cases_to_delete = (await db.execute(query)).scalars().all()
    deleted_count = len(cases_to_delete)

    for case in cases_to_delete:
        await db.delete(case)
    await db.commit()

    parsed_project_id = int(project_id.strip()) if (project_id and project_id.strip().isdigit()) else None
    updated_query = (
        select(TestCase)
        .join(Project)
        .where(Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
        .order_by(TestCase.id.desc())
    )
    if parsed_project_id:
        updated_query = updated_query.where(TestCase.project_id == parsed_project_id)
    if q and q.strip():
        updated_query = updated_query.where(TestCase.name.ilike(f"%{q.strip()}%"))

    test_cases = (await db.execute(updated_query)).scalars().all()
    res = templates.TemplateResponse("partials/scenario_table.html", {"request": request, "test_cases": test_cases})
    return trigger_toast(res, f"Berhasil menghapus {deleted_count} skenario.")


# =========================================================================
# 4. BATCH RUN & PROGRESS POLLING ROUTES
# =========================================================================
@router.post("/bulk-run")
async def process_bulk_run(
    request: Request,
    background_tasks: BackgroundTasks,
    case_ids: List[int] = Form(...),
    project_id: Optional[str] = Form(None),
    q: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Trigger background execution for selectively checked scenarios."""
    if not case_ids:
        return trigger_toast(HTMLResponse(""), "Pilih minimal 1 skenario.", "warning")

    # 🟢 1. Prioritaskan Form, lalu Query parameter
    raw_project_id = project_id or request.query_params.get("project_id")
    raw_q = q or request.query_params.get("q")

    parsed_proj_id = int(raw_project_id.strip()) if (raw_project_id and raw_project_id.strip().isdigit()) else None
    clean_q = raw_q.strip() if (raw_q and raw_q.strip()) else None

    # 🟢 2. Simpan project_id dan q ke memori BATCH_STATUS agar tidak hilang saat polling
    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    BATCH_STATUS[batch_id] = {
        "total": len(case_ids),
        "completed": 0,
        "status": "STARTING",
        "current_name": "Inisialisasi...",
        "project_id": parsed_proj_id,
        "q": clean_q
    }

    background_tasks.add_task(run_selected_scenarios, case_ids, current_user.id, settings.DATABASE_URL, batch_id)

    params = {}
    if parsed_proj_id:
        params["project_id"] = str(parsed_proj_id)
    if clean_q:
        params["q"] = clean_q
    
    query_str = f"?{urllib.parse.urlencode(params)}" if params else ""

    return HTMLResponse(f"""
        <div id="batch-progress-box" hx-get="/scenarios/batch-progress/{batch_id}{query_str}" hx-trigger="load, every 2s" hx-swap="outerHTML">
            <p class="text-xs text-indigo-600 font-bold animate-pulse">🚀 Memulai pengujian untuk {len(case_ids)} skenario terpilih...</p>
        </div>
    """)


@router.get("/batch-progress/{batch_id}")
async def get_batch_progress(
    batch_id: str,
    request: Request,
    project_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Polling endpoint for batch progress with auto OOB table update upon completion."""
    status_info = BATCH_STATUS.get(batch_id, {"total": 0, "completed": 0, "status": "IDLE", "current_name": ""})
    total = status_info["total"]
    completed = status_info["completed"]
    percentage = int((completed / total) * 100) if total > 0 else 0
    is_finished = status_info["status"] == "COMPLETED"

    # 🟢 3. Ambil active project_id dan q (utamakan parameter Query, fallback ke memori server)
    saved_project_id = status_info.get("project_id")
    saved_q = status_info.get("q")

    active_project_id = None
    if project_id and project_id.strip().isdigit():
        active_project_id = int(project_id.strip())
    elif saved_project_id:
        active_project_id = int(saved_project_id)

    active_q = q.strip() if (q and q.strip()) else saved_q

    params = {}
    if active_project_id:
        params["project_id"] = str(active_project_id)
    if active_q:
        params["q"] = active_q
    
    query_str = f"?{urllib.parse.urlencode(params)}" if params else ""
    trigger_header = 'hx-trigger="every 2s"' if not is_finished else ''

    progress_html = f"""
    <div id="batch-progress-box" hx-get="/scenarios/batch-progress/{batch_id}{query_str}" {trigger_header} hx-swap="outerHTML" class="space-y-2 p-3 bg-slate-50 border border-slate-200 rounded-xl shadow-xs mb-3">
        <div class="flex justify-between items-center text-xs font-bold text-slate-700">
            <span>{"✅ Batch Run Selesai!" if is_finished else f"⏳ Menguji: {status_info['current_name']}"}</span>
            <span>{completed} / {total} ({percentage}%)</span>
        </div>
        <div class="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
            <div class="bg-indigo-600 h-2.5 rounded-full transition-all duration-500" style="width: {percentage}%"></div>
        </div>
        {"<p class='text-[11px] text-emerald-600 font-semibold mt-1'>✨ Semua skenario selesai diuji. Status tabel telah diperbarui!</p>" if is_finished else ""}
    </div>
    """

    # 🟢 4. Render tabel dengan mengunci filter project yang aktif
    if is_finished:
        updated_query = (
            select(TestCase)
            .join(Project)
            .where(Project.user_id == current_user.id)
            .options(
                selectinload(TestCase.project),
                selectinload(TestCase.steps),
                selectinload(TestCase.runs)
            )
            .order_by(TestCase.id.desc())
        )
        if active_project_id:
            updated_query = updated_query.where(TestCase.project_id == active_project_id)
        if active_q:
            updated_query = updated_query.where(TestCase.name.ilike(f"%{active_q}%"))

        test_cases = (await db.execute(updated_query)).scalars().all()
        table_html = templates.get_template("partials/scenario_table.html").render({
            "request": request,
            "test_cases": test_cases
        })
        oob_table_html = f'<div id="scenario-table-container" hx-swap-oob="true" class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">{table_html}</div>'
        return HTMLResponse(progress_html + oob_table_html)

    return HTMLResponse(progress_html)