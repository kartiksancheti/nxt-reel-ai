import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.chat_editor import run_chat_editor
from app.ai.agents.orchestrator import run_multi_agent_director
from app.ai.validator import validate_and_fix_timeline
from app.services.retake_detector import detect_and_filter_retakes
from app.api.deps import get_db
from app.db.models import Project, ProjectStatus
from app.models.project import ProjectOut
from app.models.timeline import Segment, Timeline

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

        original_count = len(segments)
        segments = detect_and_filter_retakes(segments)
        if len(segments) < original_count:
            logger.info(
                "Retake detector removed %d segment(s) for project=%s",
                original_count - len(segments), project_id,
            )

        duration = segments[-1].end if segments else 0.0

        timeline, treatment = run_multi_agent_director(
            segments=segments,
            project_id=str(project.id),
            style_preset=project.style_preset,
            duration=duration,
            caption_overrides=project.caption_overrides,
            layout=project.layout or "full",
        )
        timeline = validate_and_fix_timeline(timeline)
        project.timeline_json = timeline.model_dump()
        project.creative_treatment = treatment
        project.status = ProjectStatus.TIMELINE_READY
    except Exception as exc:  # noqa: BLE001
        logger.exception("Timeline generation failed for project=%s", project_id)
        project.status = ProjectStatus.FAILED
        project.error_message = str(exc)

    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/timeline/{project_id}")
async def get_timeline_detail(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": str(project.id),
        "transcript": project.transcript,
        "creative_treatment": project.creative_treatment,
        "timeline_json": project.timeline_json,
    }


class ChatEditRequest(BaseModel):
    message: str


class ChatEditResponse(BaseModel):
    notes: str
    unsupported: bool
    status: str


@router.post("/chat-edit/{project_id}", response_model=ChatEditResponse)
async def chat_edit_timeline(
    project_id: uuid.UUID, body: ChatEditRequest, db: AsyncSession = Depends(get_db)
) -> ChatEditResponse:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.timeline_json:
        raise HTTPException(status_code=400, detail="Project has no generated timeline yet")

    timeline = Timeline.model_validate(project.timeline_json)
    patch = run_chat_editor(timeline.segments, body.message)

    if patch.get("unsupported_request"):
        return ChatEditResponse(
            notes=patch.get("notes", "That request isn't supported yet."),
            unsupported=True,
            status=project.status,
        )

    caption_updates = patch.get("caption_style_updates") or {}
    if caption_updates:
        timeline.caption_style = timeline.caption_style.model_copy(update=caption_updates)

    remove_ids = set(patch.get("remove_visual_segment_ids") or [])
    if remove_ids:
        timeline.visual_events = [
            e for e in timeline.visual_events if e.segment_id not in remove_ids
        ]

    cta_text = patch.get("cta_text")
    if cta_text:
        for cta in timeline.cta_events:
            cta.text = cta_text

    timeline = validate_and_fix_timeline(timeline)
    project.timeline_json = timeline.model_dump()

    if project.status in (ProjectStatus.RENDERED, ProjectStatus.EXPORTED):
        project.status = ProjectStatus.TIMELINE_READY
        project.rendered_video_path = None
        project.exported_video_path = None

    await db.commit()
    await db.refresh(project)

    return ChatEditResponse(
        notes=patch.get("notes", "Change applied — press Render again to see it."),
        unsupported=False,
        status=project.status,
    )
