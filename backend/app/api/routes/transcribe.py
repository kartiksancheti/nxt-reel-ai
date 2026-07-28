import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.transcription import build_segments, extract_audio, transcribe_audio
from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import Project, ProjectStatus
from app.models.project import ProjectOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transcribe"])


@router.post("/transcribe/{project_id}", response_model=ProjectOut)
async def transcribe_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.source_video_path:
        raise HTTPException(status_code=400, detail="Project has no uploaded video")

    settings = get_settings()
    project.status = ProjectStatus.TRANSCRIBING
    await db.commit()

    try:
        audio_path = extract_audio(project.source_video_path, settings.uploads_dir)
        whisper_result = transcribe_audio(audio_path)
        segments = build_segments(whisper_result)

        project.transcript = {"segments": [s.model_dump() for s in segments]}
        project.status = ProjectStatus.TRANSCRIBED
    except Exception as exc:  # noqa: BLE001 - surface any failure onto the project
        logger.exception("Transcription failed for project=%s", project_id)
        project.status = ProjectStatus.FAILED
        project.error_message = str(exc)

    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)
