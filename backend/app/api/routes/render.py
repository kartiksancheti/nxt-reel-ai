import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.db.models import Project, ProjectStatus
from app.models.project import ProjectOut
from app.services.render_service import render_project_task
logger = logging.getLogger(__name__)
router = APIRouter(tags=["render"])
@router.post("/render/{project_id}", response_model=ProjectOut)
async def render_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.timeline_json:
        raise HTTPException(status_code=400, detail="Project has no generated timeline yet")
    project.status = ProjectStatus.RENDERING
    await db.commit()
    logger.info("Queuing render job for project=%s", project_id)
    render_project_task.delay(
        str(project.id), project.timeline_json, project.source_video_path,
        project.segment_clip_overrides or {},
    )
    await db.refresh(project)
    return ProjectOut.model_validate(project)
