import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import Project
from app.models.project import ProjectOut, ProjectStatusOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["project"])


@router.get("/project/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectOut.model_validate(project)


@router.get("/status/{project_id}", response_model=ProjectStatusOut)
async def get_project_status(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectStatusOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectStatusOut(
        id=str(project.id), status=project.status, error_message=project.error_message
    )


@router.delete("/project/{project_id}")
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    logger.info("Deleting project=%s", project_id)
    await db.delete(project)
    await db.commit()
    return {"deleted": True, "id": str(project_id)}
