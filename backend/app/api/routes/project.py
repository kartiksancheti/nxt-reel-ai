import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import Project
from app.models.project import ProjectOut, ProjectStatusOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["project"])


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[ProjectOut]:
    """List every project, newest first — powers the dashboard's project
    history view."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [ProjectOut.model_validate(p) for p in projects]


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


@router.get("/download/{project_id}")
async def download_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Serve the finished video file directly — prefers the exported
    copy, falls back to the raw rendered one if export hasn't run yet."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    video_path = project.exported_video_path or project.rendered_video_path
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=400, detail="No finished video available for this project yet")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"nxt-reel-{project_id}.mp4",
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
