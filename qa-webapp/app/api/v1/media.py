import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.core.config import settings

router = APIRouter(tags=["Media"])

@router.get("/videos/{video_name}")
async def stream_video(video_name: str, request: Request):
    video_path = os.path.join(settings.VIDEO_DIR, video_name)
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

    return StreamingResponse(iterfile(), status_code=206, headers=headers, media_type="video/webm")