from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.models import TestCase, Project
from app.services.export_service import generate_ut_matrix_excel

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/ut-matrix")
async def export_ut_matrix(
    project_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint untuk mendownload Laporan UT Document Matrix dalam format Excel (.xlsx).
    Dapat difilter berdasarkan project_id tertentu atau mengekspor seluruh proyek.
    """
    query = select(TestCase).options(
        selectinload(TestCase.project),
        selectinload(TestCase.steps),
        selectinload(TestCase.runs)
    ).order_by(TestCase.id.asc())

    project_name = "All_Projects"

    if project_id:
        proj_result = await db.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Proyek tidak ditemukan.")
        project_name = project.name.replace(" ", "_")
        query = query.where(TestCase.project_id == project_id)

    result = await db.execute(query)
    test_cases = result.scalars().all()

    if not test_cases:
        raise HTTPException(status_code=400, detail="Tidak ada data skenario pengujian untuk diekspor.")

    excel_stream = generate_ut_matrix_excel(test_cases, project_name=project_name)
    filename = f"UT_Document_Matrix_{project_name}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )