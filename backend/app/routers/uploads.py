import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..paths import UPLOAD_DIR

router = APIRouter()

ALLOWED_TYPES = {"transcript", "screenshot", "video_recording"}

# Generous enough for a full meeting recording, while still guarding against
# an accidental multi-GB upload silently filling the disk.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024


@router.post("/{project_id}/uploads", response_model=schemas.UploadedFileOut, status_code=201)
async def upload_file(
    project_id: int,
    type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="type must be one of: " + ", ".join(sorted(ALLOWED_TYPES)))

    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Strip any directory components from the client-supplied name so a
    # crafted filename (e.g. "../../etc/passwd") can't escape the project's
    # upload folder.
    safe_name = Path(file.filename or "upload").name
    project_dir = UPLOAD_DIR / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    dest_path = project_dir / safe_name

    try:
        written = 0
        with dest_path.open("wb") as out:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the 2GB upload limit")
                out.write(chunk)
    except HTTPException:
        dest_path.unlink(missing_ok=True)
        raise

    record = models.UploadedFile(
        project_id=project_id,
        type=type,
        filename=safe_name,
        storage_path=str(dest_path),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{project_id}/uploads", response_model=list[schemas.UploadedFileOut])
def list_uploads(project_id: int, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.project_id == project_id)
        .order_by(models.UploadedFile.uploaded_at.asc())
        .all()
    )


@router.get("/{project_id}/uploads/{file_id}/content")
def get_upload_content(project_id: int, file_id: int, db: Session = Depends(get_db)):
    record = db.get(models.UploadedFile, file_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="File not found")

    path = Path(record.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")

    media_type = mimetypes.guess_type(record.filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=record.filename)
