"""Upload, download, and delete documents attached to completion events."""

from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attachment, ComplianceEvent

router = APIRouter(prefix="/api", tags=["attachments"])

UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads")),
)
MAX_BYTES = 20 * 1024 * 1024  # 20 MB per file

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "file")
    name = _SAFE.sub("_", name).strip("._") or "file"
    return name[:200]


@router.post("/events/{event_id}/attachments", status_code=201)
async def upload_attachment(
    event_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    event = db.get(ComplianceEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 20 MB)")

    dest_dir = os.path.join(UPLOAD_DIR, str(event_id))
    os.makedirs(dest_dir, exist_ok=True)
    safe = _safe_name(file.filename)
    dest = os.path.join(dest_dir, safe)
    # Avoid clobbering an existing file with the same name.
    base, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(dest):
        dest = f"{base}_{n}{ext}"
        n += 1
    with open(dest, "wb") as f:
        f.write(data)

    att = Attachment(
        compliance_event_id=event_id,
        filename=os.path.basename(dest),
        content_type=file.content_type,
        size_bytes=len(data),
        storage_path=dest,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return {"id": att.id, "filename": att.filename, "size_bytes": att.size_bytes}


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    att = db.get(Attachment, attachment_id)
    if not att or not os.path.exists(att.storage_path):
        raise HTTPException(404, "Attachment not found")
    return FileResponse(
        att.storage_path,
        media_type=att.content_type or "application/octet-stream",
        filename=att.filename,
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    att = db.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(404, "Attachment not found")
    try:
        if os.path.exists(att.storage_path):
            os.remove(att.storage_path)
    except OSError:
        pass
    db.delete(att)
    db.commit()
