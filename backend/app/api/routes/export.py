import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import Project, ProjectStatus
from app.models.project import ProjectOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["export"])


@router.post("/export/{project_id}", response_model=ProjectOut)
async def export_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != ProjectStatus.RENDERED or not project.rendered_video_path:
        raise HTTPException(status_code=400, detail="Project has not finished rendering yet")

    settings = get_settings()
    export_dir = Path(settings.renders_dir) / str(project.id) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / "final_export.mp4"

    logger.info("Exporting project=%s -> %s", project_id, export_path)
    shutil.copy(project.rendered_video_path, export_path)

    project.exported_video_path = str(export_path)
    project.status = ProjectStatus.EXPORTED
    await db.commit()
    await db.refresh(project)

    return ProjectOut.model_validate(project)
