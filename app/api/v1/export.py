import os
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.api.v1.dashboard import trigger_toast
from app.models.models import TestCase, Project, TestRun, User
from app.services.export_service import generate_ut_matrix_excel

router = APIRouter(prefix="/export", tags=["Export"])
templates = Jinja2Templates(directory="templates")

@router.get("/modal")
async def get_export_modal(
    request: Request,
    project_id: Optional[str] = Query(None),  # ✅ Diubah ke Optional[str] agar kebal terhadap project_id=
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # 🔒 Proteksi Login
):
    """Menampilkan modal ringkasan status skenario sebelum diekspor."""
    # Konversi aman dari string ke integer
    parsed_project_id: Optional[int] = None
    if project_id and project_id.strip().isdigit():
        parsed_project_id = int(project_id.strip())

    # Pastikan hanya mengambil data dari proyek milik current_user
    base_query = select(TestCase).join(Project).where(Project.user_id == current_user.id)
    if parsed_project_id:
        base_query = base_query.where(TestCase.project_id == parsed_project_id)

    cases_result = await db.execute(base_query.options(selectinload(TestCase.runs)))
    cases = cases_result.scalars().all()

    total_cases = len(cases)
    success_count = 0
    failed_count = 0
    untested_count = 0

    for tc in cases:
        if not tc.runs:
            untested_count += 1
        else:
            latest_run = sorted(tc.runs, key=lambda r: r.executed_at, reverse=True)[0]
            if latest_run.status == "SUCCESS":
                success_count += 1
            elif latest_run.status == "FAILED":
                failed_count += 1
            else:
                untested_count += 1

    return templates.TemplateResponse("partials/export_modal.html", {
        "request": request,
        "project_id": parsed_project_id,
        "total_cases": total_cases,
        "success_count": success_count,
        "failed_count": failed_count,
        "untested_count": untested_count
    })

@router.get("/ut-matrix")
async def export_ut_matrix(
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Endpoint untuk mendownload Laporan UT Document Matrix & Evidence (.xlsx) sekaligus mereset status skenario ke UNTESTED."""
    # 1. Konversi aman dari string ke integer
    parsed_project_id: Optional[int] = None
    if project_id and project_id.strip().isdigit():
        parsed_project_id = int(project_id.strip())

    # 2. Ambil data skenario milik current_user
    query = select(TestCase).join(Project).where(Project.user_id == current_user.id).options(
        selectinload(TestCase.project),
        selectinload(TestCase.steps),
        selectinload(TestCase.runs)
    ).order_by(TestCase.id.asc())

    if parsed_project_id:
        query = query.where(TestCase.project_id == parsed_project_id)

    result = await db.execute(query)
    test_cases = result.scalars().all()

    if not test_cases:
        raise HTTPException(status_code=404, detail="Tidak ada skenario tes ditemukan pada proyek ini.")

    project_name = "All_Projects"
    if parsed_project_id:
        proj_result = await db.execute(select(Project).where(Project.id == parsed_project_id, Project.user_id == current_user.id))
        proj = proj_result.scalar_one_or_none()
        if proj:
            project_name = proj.name.replace(" ", "_")

    # 3. Generate Excel passing current_user.id
    excel_stream, screenshots_to_delete = generate_ut_matrix_excel(
        test_cases, 
        project_name=project_name, 
        user_id=current_user.id
    )
    filename = f"UT_Document_Matrix_{project_name}.xlsx"

    # 4. Clean up user screenshot evidence files after export
    for filepath in screenshots_to_delete:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"[Cleanup Screenshot Warning] Could not remove {filepath}: {e}")

    # 5. 🛠️ RESET STATUS: Hapus entri TestRun & video terkait agar status kembali ke UNTESTED
    case_ids = [tc.id for tc in test_cases]
    if case_ids:
        runs_query = select(TestRun).where(TestRun.test_case_id.in_(case_ids))
        runs_result = await db.execute(runs_query)
        runs_to_delete = runs_result.scalars().all()

        for run in runs_to_delete:
            # Hapus berkas video jika masih tersisa
            if run.video_url:
                video_filename = run.video_url.split("/")[-1]
                video_filepath = os.path.join("static", "videos", video_filename)
                if os.path.exists(video_filepath):
                    try:
                        os.remove(video_filepath)
                    except Exception:
                        pass
            await db.delete(run)

        await db.commit()

    # 6. Stream file Excel ke browser pengguna
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.post("/bulk-modal")
async def get_bulk_export_modal(
    request: Request,
    case_ids: list[int] = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render confirmation modal for exporting selected scenarios."""
    if not case_ids:
        return trigger_toast(HTMLResponse(""), "No scenarios selected.", "warning")

    query = (
        select(TestCase)
        .join(Project)
        .where(TestCase.id.in_(case_ids), Project.user_id == current_user.id)
        .options(selectinload(TestCase.project)) 
    )
    cases = (await db.execute(query)).scalars().all()

    return templates.TemplateResponse("partials/bulk_export_modal.html", {
        "request": request,
        "selected_cases": cases,
        "case_ids": case_ids 
    })

@router.post("/bulk-download")
async def process_bulk_export_download(
    case_ids: list[int] = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate and download a single Excel file containing multiple selected scenarios."""
    if not case_ids:
        raise HTTPException(status_code=400, detail="Tidak ada skenario yang dipilih")

    # 1. Ambil data skenario beserta project, step, dan riwayat eksekusinya
    query = (
        select(TestCase)
        .join(Project)
        .where(TestCase.id.in_(case_ids), Project.user_id == current_user.id)
        .options(
            selectinload(TestCase.project),
            selectinload(TestCase.steps),
            selectinload(TestCase.runs)
        )
        .order_by(TestCase.id.asc())
    )
    selected_cases = (await db.execute(query)).scalars().all()

    if not selected_cases:
        raise HTTPException(status_code=404, detail="Skenario tidak ditemukan")

    # 2. Tentukan nama proyek (string) untuk header dan nama file
    project_name = selected_cases[0].project.name.replace(" ", "_") if selected_cases[0].project else "Bulk_Export"

    # 3. 🟢 Bongkar tuple hasil return (excel_stream & screenshots_to_delete)
    excel_stream, screenshots_to_delete = generate_ut_matrix_excel(
        selected_cases, 
        project_name=project_name, 
        user_id=current_user.id
    )

    # 4. Bersihkan file screenshot sementara jika ada
    for filepath in screenshots_to_delete:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"[Cleanup Screenshot Warning] Could not remove {filepath}: {e}")

    file_name = f"UT_Document_Batch_{len(selected_cases)}_Scenarios.xlsx"

    # 5. Stream file Excel langsung ke browser
    return StreamingResponse(
        excel_stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"'
        }
    )