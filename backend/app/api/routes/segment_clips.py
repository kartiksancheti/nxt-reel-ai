"""
Segment Clip Overrides.

Lets a person upload their OWN video for a specific segment (a real
dashboard/chat demo recording, a manually-generated AI video clip, etc.)
instead of relying on the Konva/Lottie scene or stock footage for that
moment. This is the safe, no-credentials alternative to trying to
automate logins into private tools — the person records/generates the
clip themselves, once, and tags it to the exact moment it belongs to.
"""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import Project

logger = logging.getLogger(__name__)
router = APIRouter(tags=["segment-clips"])

CHUNK_SIZE = 1024 * 1024


@router.post("/segment-clip/{project_id}/{segment_id}")
async def upload_segment_clip(
    project_id: uuid.UUID,
    segment_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    clip_dir = Path(settings.uploads_dir) / str(project.id) / "segment_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    dest_path = clip_dir / f"{segment_id}_{file.filename}"

    with open(dest_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)

    overrides = dict(project.segment_clip_overrides or {})
    overrides[segment_id] = str(dest_path)
    project.segment_clip_overrides = overrides

    await db.commit()
    logger.info("Segment clip override saved for project=%s segment=%s -> %s", project_id, segment_id, dest_path)
    return {"segment_id": segment_id, "path": str(dest_path), "overrides": overrides}


@router.get("/segment-clip/{project_id}")
async def list_segment_clips(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"overrides": project.segment_clip_overrides or {}}


@router.delete("/segment-clip/{project_id}/{segment_id}")
async def delete_segment_clip(project_id: uuid.UUID, segment_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    overrides = dict(project.segment_clip_overrides or {})
    removed_path = overrides.pop(segment_id, None)
    project.segment_clip_overrides = overrides
    await db.commit()

    if removed_path:
        try:
            Path(removed_path).unlink(missing_ok=True)
        except Exception:
            logger.exception("Failed to delete override file %s", removed_path)

    return {"segment_id": segment_id, "removed": bool(removed_path)}
