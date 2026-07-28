import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.orchestrator import run_multi_agent_director
from app.ai.validator import validate_and_fix_timeline
from app.api.deps import get_db
from app.db.models import Project, ProjectStatus
from app.models.project import ProjectOut
from app.models.timeline import Segment

logger = logging.getLogger(__name__)
router = APIRouter(tags=["timeline"])


@router.post("/generate-timeline/{project_id}", response_model=ProjectOut)
async def generate_timeline(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.transcript:
        raise HTTPException(status_code=400, detail="Project has not been transcribed yet")

    project.status = ProjectStatus.GENERATING_TIMELINE
    await db.commit()

    try:
        segments = [Segment(**s) for s in project.transcript["segments"]]
        duration = segments[-1].end if segments else 0.0

        timeline = run_multi_agent_director(
            segments=segments,
            project_id=str(project.id),
            style_preset=project.style_preset,
            duration=duration,
        )
        timeline = validate_and_fix_timeline(timeline)
        project.timeline_json = timeline.model_dump()
        project.status = ProjectStatus.TIMELINE_READY
    except Exception as exc:  # noqa: BLE001
        logger.exception("Timeline generation failed for project=%s", project_id)
        project.status = ProjectStatus.FAILED
        project.error_message = str(exc)

    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)
