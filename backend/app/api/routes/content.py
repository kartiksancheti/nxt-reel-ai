"""
Post-export content generation: Instagram captions and YouTube
descriptions. Deliberately separate from the video render pipeline —
these only need a transcript, not a finished render.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.caption_writer import run_caption_writer
from app.ai.agents.description_writer import run_description_writer
from app.api.deps import get_db
from app.db.models import Project
from app.models.timeline import Segment

logger = logging.getLogger(__name__)
router = APIRouter(tags=["content"])


@router.post("/generate-caption/{project_id}")
async def generate_caption(
    project_id: uuid.UUID,
    cta_keyword: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.transcript:
        raise HTTPException(status_code=400, detail="Project has not been transcribed yet")

    transcript_text = " ".join(s["text"] for s in project.transcript["segments"])
    variants = run_caption_writer(transcript_text, cta_keyword=cta_keyword)
    return {"project_id": str(project_id), "variants": variants}


@router.post("/generate-description/{project_id}")
async def generate_description(
    project_id: uuid.UUID,
    cta_keyword: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.transcript:
        raise HTTPException(status_code=400, detail="Project has not been transcribed yet")

    segments = [Segment(**s) for s in project.transcript["segments"]]
    result = run_description_writer(segments, cta_keyword=cta_keyword)
    return {"project_id": str(project_id), **result}
