import hashlib
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import Project, ProjectStatus
from app.models.project import ProjectOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

CHUNK_SIZE = 1024 * 1024


@router.post("/upload", response_model=ProjectOut)
async def upload_video(
    file: UploadFile,
    style_preset: str = Form(default="minimal"),
    layout: str = Form(default="full"),
    expected_md5: str | None = Form(default=None),
    caption_font: str | None = Form(default=None),
    caption_color: str | None = Form(default=None),
    caption_highlight_color: str | None = Form(default=None),
    caption_position: str | None = Form(default=None),
    caption_animation: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """Accept a talking-head video upload and create a new Project.

    `layout` selects the overall visual layout: "full" (default — normal
    full-frame speaker with B-roll cutaways) or "split_demo" (top half is
    a Konva.js-generated demo graphic, bottom half is the speaker,
    continuously, for the whole video)."""
    settings = get_settings()
    project = Project(style_preset=style_preset, layout=layout, status=ProjectStatus.UPLOADED)

    overrides = {
        k: v
        for k, v in {
            "font": caption_font,
            "color": caption_color,
            "highlight_color": caption_highlight_color,
            "position": caption_position,
            "animation": caption_animation,
        }.items()
        if v
    }
    if overrides:
        project.caption_overrides = overrides

    db.add(project)
    await db.flush()

    upload_dir = Path(settings.uploads_dir) / str(project.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / file.filename

    logger.info("Saving upload for project=%s to %s", project.id, dest_path)

    hasher = hashlib.md5()
    bytes_written = 0
    with open(dest_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
            hasher.update(chunk)
            bytes_written += len(chunk)

    actual_md5 = hasher.hexdigest()
    logger.info(
        "Upload written for project=%s: %d bytes, md5=%s (expected=%s)",
        project.id, bytes_written, actual_md5, expected_md5,
    )

    if expected_md5 and expected_md5.lower() != actual_md5.lower():
        logger.error(
            "Upload corruption detected for project=%s: expected md5=%s, got md5=%s — rejecting",
            project.id, expected_md5, actual_md5,
        )
        dest_path.unlink(missing_ok=True)
        await db.delete(project)
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail=(
                f"Upload corrupted in transit (expected md5={expected_md5}, "
                f"got md5={actual_md5}). This project was not created — "
                "please retry the upload."
            ),
        )

    project.source_video_path = str(dest_path)
    await db.commit()
    await db.refresh(project)

    return ProjectOut.model_validate(project)
