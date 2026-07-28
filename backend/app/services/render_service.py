"""
Render Engine.

The final, "dumb" executor. By the time a Timeline reaches this module,
every creative decision has already been made — this only ever resolves
visual events through the right engine, then composites everything with
MoviePy/FFmpeg exactly as instructed. No creative judgment happens here,
by design.
"""
import logging
from pathlib import Path

import PIL.Image

if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.models import Project, ProjectStatus
from app.engines.audio_engine import resolve_audio_assets
from app.engines.browser_engine import BrowserEngine
from app.engines.image_gen_engine import ImageGenerationEngine
from app.engines.motion_graphics_engine import MotionGraphicsEngine
from app.engines.stock_engine import StockFootageEngine
from app.engines.ui_template_engine import UITemplateEngine
from app.models.timeline import CameraMove, Timeline, VisualSource

logger = logging.getLogger(__name__)

ENGINE_MAP = {
    VisualSource.BROWSER: BrowserEngine(),
    VisualSource.STOCK_FOOTAGE: StockFootageEngine(),
    VisualSource.MOTION_GRAPHICS: MotionGraphicsEngine(),
    VisualSource.IMAGE_GENERATION: ImageGenerationEngine(),
    VisualSource.UI_TEMPLATE: UITemplateEngine(),
}

TARGET_RESOLUTION = (1080, 1920)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
CUT_GAP_SECONDS = 0.06  # tiny breathing room between jump cuts so audio doesn't click


async def resolve_visual_assets(timeline: Timeline) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for event in timeline.visual_events:
        if event.source == VisualSource.ORIGINAL_FOOTAGE:
            continue
        engine = ENGINE_MAP.get(VisualSource(event.source))
        if engine is None:
            logger.warning("No engine registered for source=%s", event.source)
            continue
        try:
            asset_path = await engine.resolve(event, timeline.project_id)
            resolved[event.segment_id] = asset_path
        except Exception:
            logger.exception(
                "Failed to resolve visual asset for segment=%s source=%s — skipping it",
                event.segment_id, event.source,
            )
            continue
    return resolved


def _db_to_volume_ratio(db: float) -> float:
    return 10 ** (db / 20)


def _fit_to_target(clip):
    target_w, target_h = TARGET_RESOLUTION
    clip_ratio = clip.w / clip.h
    target_ratio = target_w / target_h

    if clip_ratio > target_ratio:
        resized = clip.resize(height=target_h)
        resized = resized.crop(x_center=resized.w / 2, width=target_w)
    else:
        resized = clip.resize(width=target_w)
        resized = resized.crop(y_center=resized.h / 2, height=target_h)
    return resized


def _apply_camera_move(clip, move: str, duration: float):
    if move == CameraMove.ZOOM_IN:
        return clip.fx(vfx.resize, lambda t: 1 + 0.04 * (t / max(duration, 0.01)))
    if move == CameraMove.ZOOM_OUT:
        return clip.fx(vfx.resize, lambda t: 1.15 - 0.15 * (t / max(duration, 0.01)))
    if move == CameraMove.PAN_LEFT:
        return clip.set_position(lambda t: (-20 * (t / max(duration, 0.01)), "center"))
    if move == CameraMove.PAN_RIGHT:
        return clip.set_position(lambda t: (20 * (t / max(duration, 0.01)), "center"))
    return clip


def _load_visual_clip(asset_path: str, duration: float):
    ext = Path(asset_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        clip = ImageClip(asset_path).set_duration(duration)
    else:
        clip = VideoFileClip(asset_path, has_mask=(ext == ".mov"))
        if clip.duration < duration:
            clip = clip.fx(vfx.loop, duration=duration)
        else:
            clip = clip.subclip(0, duration)
        clip = clip.without_audio()
    return clip


class CutPlan:
    """Maps a Timeline's original (raw-footage) timestamps to a new,
    jump-cut timeline that only includes the segments where someone is
    actually speaking — pauses and dead air between segments are removed
    entirely, which is what creates fast, punchy pacing.

    Every overlay (B-roll, motion graphics, captions, CTAs) is keyed to a
    segment_id, so once we know each segment's shift (new_start - old_start),
    we can re-time any event that belongs to that segment.
    """

    def __init__(self, timeline: Timeline):
        segments = sorted(timeline.segments, key=lambda s: s.start)
        self.cut_ranges: list[tuple[float, float]] = []
        self.shift_by_segment: dict[str, float] = {}
        self.new_start_by_segment: dict[str, float] = {}

        cursor = 0.0
        for seg in segments:
            duration = max(seg.end - seg.start, 0.05)
            self.cut_ranges.append((seg.start, seg.end))
            self.shift_by_segment[seg.id] = cursor - seg.start
            self.new_start_by_segment[seg.id] = cursor
            cursor += duration + CUT_GAP_SECONDS
        self.total_duration = max(cursor - CUT_GAP_SECONDS, 0.1)

    def shift_for_segment(self, segment_id: str) -> float:
        return self.shift_by_segment.get(segment_id, 0.0)

    def new_start_for_segment(self, segment_id: str) -> float | None:
        return self.new_start_by_segment.get(segment_id)


def _build_cut_base_clip(source_video_path: str, cut_plan: CutPlan):
    """Concatenate only the speaking segments from the source footage,
    back to back — this is the actual jump-cut edit."""
    source = VideoFileClip(source_video_path)
    subclips = []
    for start, end in cut_plan.cut_ranges:
        end = min(end, source.duration)
        start = min(start, end)
        if end - start <= 0:
            continue
        subclips.append(source.subclip(start, end))
    if not subclips:
        return _fit_to_target(source)
    cut = concatenate_videoclips(subclips, method="compose")
    return _fit_to_target(cut)


def _build_visual_overlay_clips(timeline: Timeline, resolved_assets: dict[str, str], cut_plan: CutPlan) -> list:
    events = sorted(
        (e for e in timeline.visual_events if e.segment_id in resolved_assets),
        key=lambda e: e.z_index,
    )
    clips = []
    for event in events:
        asset_path = resolved_assets[event.segment_id]
        duration = max(event.end - event.start, 0.1)
        if event.source == VisualSource.MOTION_GRAPHICS:
            duration = min(duration, 5.0)  # motion graphics are short overlays, never full-video-length
        shift = cut_plan.shift_for_segment(event.segment_id)
        new_start = max(event.start + shift, 0.0)
        try:
            clip = _load_visual_clip(asset_path, duration)
            clip = _fit_to_target(clip)
            clip = _apply_camera_move(clip, event.camera_move, duration)
            clip = clip.set_start(new_start).set_duration(duration)
            clips.append(clip)
        except Exception:
            logger.exception(
                "Failed to composite visual asset for segment=%s (%s) — skipping",
                event.segment_id, asset_path,
            )
    return clips


def _build_kinetic_caption_clips(timeline: Timeline, cut_plan: CutPlan) -> list:
    """One TextClip per word, timed to when it's actually spoken (kinetic
    captions), positioned per the Timeline's caption_style. Falls back to
    one clip for the whole segment if word-level timing isn't available."""
    style = timeline.caption_style
    clips = []
    y_position = {"top": ("center", 200), "center": "center", "bottom": ("center", "bottom")}.get(
        style.position, "center"
    )

    for segment in timeline.segments:
        if not segment.text.strip():
            continue
        new_seg_start = cut_plan.new_start_for_segment(segment.id)
        if new_seg_start is None:
            continue
        shift = new_seg_start - segment.start

        if segment.words:
            for word in segment.words:
                if not word.text.strip():
                    continue
                w_start = max(word.start + shift, 0.0)
                # Clamp to this segment's own end — Whisper's word
                # timestamps occasionally run slightly past the segment
                # boundary, which otherwise makes this caption briefly
                # overlap the next segment's caption after the cut.
                clamped_end = min(word.end, segment.end)
                w_duration = max(clamped_end - word.start, 0.08)
                try:
                    txt_clip = (
                        TextClip(
                            word.text,
                            fontsize=style.size,
                            color=style.highlight_color,
                            font="Liberation-Sans-Bold",
                            method="label",
                            stroke_color="black",
                            stroke_width=2,
                        )
                        .set_position(y_position)
                        .set_start(w_start)
                        .set_duration(w_duration)
                    )
                    clips.append(txt_clip)
                except Exception:
                    logger.exception(
                        "Failed to render word caption '%s' in segment=%s — skipping",
                        word.text, segment.id,
                    )
        else:
            # Whisper didn't return real word-level timing for this
            # segment. Rather than fall back to one static block of
            # text (which reads as "plain, no kinetic effect"),
            # synthesize evenly-spaced word timing across the
            # segment's own duration so captions are always kinetic.
            words = segment.text.split()
            if not words:
                continue
            per_word = max(segment.end - segment.start, 0.1) / len(words)
            for i, word_text in enumerate(words):
                w_start = max(segment.start + shift + i * per_word, 0.0)
                w_duration = max(per_word, 0.08)
                try:
                    txt_clip = (
                        TextClip(
                            word_text,
                            fontsize=style.size,
                            color=style.highlight_color,
                            font="Liberation-Sans-Bold",
                            method="label",
                            stroke_color="black",
                            stroke_width=2,
                        )
                        .set_position(y_position)
                        .set_start(w_start)
                        .set_duration(w_duration)
                    )
                    clips.append(txt_clip)
                except Exception:
                    logger.exception(
                        "Failed to render synthesized word caption '%s' in segment=%s — skipping",
                        word_text, segment.id,
                    )

    return clips


def _build_cta_clips(timeline: Timeline, cut_plan: CutPlan) -> list:
    clips = []
    for cta in timeline.cta_events:
        duration = max(cta.end - cta.start, 0.1)
        shift = cut_plan.shift_for_segment(cta.segment_id)
        new_start = max(cta.start + shift, 0.0)
        try:
            txt_clip = (
                TextClip(
                    cta.text,
                    fontsize=60,
                    color="#FFE600",
                    font="Liberation-Sans-Bold",
                    method="caption",
                    size=(int(TARGET_RESOLUTION[0] * 0.8), None),
                    align="center",
                )
                .set_position(("center", int(TARGET_RESOLUTION[1] * 0.75)))
                .set_start(new_start)
                .set_duration(duration)
            )
            clips.append(txt_clip)
        except Exception:
            logger.exception("Failed to render CTA for segment=%s — skipping", cta.segment_id)
    return clips


def _build_audio_track(timeline: Timeline, base_audio):
    """Mix music/SFX against the (already jump-cut) dialogue track. Note:
    music/SFX events still reference the ORIGINAL timeline, not the cut
    one, since they aren't tied to a segment_id — this is a known
    simplification until a real music library is wired in."""
    layers = []
    if base_audio is not None:
        layers.append(base_audio)

    settings = get_settings()
    for event in timeline.audio_events:
        candidate_path = Path(settings.assets_dir) / "music" / f"{event.asset_ref}.mp3"
        if not candidate_path.exists():
            logger.warning(
                "Audio asset '%s' not found on disk (kind=%s) — skipping", event.asset_ref, event.kind
            )
            continue
        try:
            duration = max(event.end - event.start, 0.1)
            clip = AudioFileClip(str(candidate_path))
            if clip.duration < duration:
                clip = clip.fx(vfx.loop, duration=duration)
            else:
                clip = clip.subclip(0, duration)
            clip = clip.volumex(_db_to_volume_ratio(event.volume_db)).set_start(event.start)
            layers.append(clip)
        except Exception:
            logger.exception("Failed to load audio asset '%s' — skipping", event.asset_ref)

    if not layers:
        return None
    return CompositeAudioClip(layers)


def composite_timeline(
    timeline: Timeline,
    source_video_path: str,
    resolved_assets: dict[str, str],
    output_path: str,
) -> str:
    logger.info(
        "Compositing timeline for project=%s -> %s (%d visual, %d audio, %d cta events)",
        timeline.project_id, output_path,
        len(timeline.visual_events), len(timeline.audio_events), len(timeline.cta_events),
    )

    cut_plan = CutPlan(timeline)
    base = _build_cut_base_clip(source_video_path, cut_plan)
    base = base.set_duration(min(base.duration, cut_plan.total_duration or base.duration))

    layers = [base]
    layers.extend(_build_visual_overlay_clips(timeline, resolved_assets, cut_plan))
    layers.extend(_build_kinetic_caption_clips(timeline, cut_plan))
    layers.extend(_build_cta_clips(timeline, cut_plan))

    final = CompositeVideoClip(layers, size=TARGET_RESOLUTION).set_duration(base.duration)

    audio_track = _build_audio_track(timeline, base.audio)
    if audio_track is not None:
        # Music/SFX events are timed against the ORIGINAL uncut
        # duration, but jump cuts shorten the final video — without
        # this, background music keeps playing past the video's end.
        audio_track = audio_track.set_duration(final.duration)
        final = final.set_audio(audio_track)

    logger.info("Writing final video to %s", output_path)
    final.write_videofile(
        output_path,
        fps=timeline.fps or 30,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="ultrafast",
    )

    for layer in layers:
        try:
            layer.close()
        except Exception:
            pass

    return output_path


async def _mark_project_status(
    project_id: str,
    status: ProjectStatus,
    error_message: str | None = None,
    rendered_path: str | None = None,
) -> None:
    """Update a project's status using a FRESH, short-lived database
    engine created within this task's own event loop.

    Celery's prefork worker runs each task via a fresh asyncio.run()
    call, which creates a brand-new event loop every time. AsyncPG
    connections are bound to the event loop they were created under, so
    reusing a shared, module-level engine/pool across tasks causes
    "attached to a different loop" errors once a second task runs.
    Creating (and disposing) the engine locally, inside this same
    coroutine, guarantees the connection always matches the loop
    actually in use."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_local() as session:
            project = await session.get(Project, project_id)
            if project is None:
                logger.warning("Project %s not found when updating status to %s", project_id, status)
                return
            project.status = status
            project.error_message = error_message
            if rendered_path is not None:
                project.rendered_video_path = rendered_path
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="render_project")
def render_project_task(project_id: str, timeline_dict: dict, source_video_path: str) -> str:
    import asyncio

    async def _run() -> str:
        settings = get_settings()
        timeline = Timeline.model_validate(timeline_dict)

        output_dir = Path(settings.renders_dir) / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / "final.mp4")

        try:
            resolved_assets = await resolve_visual_assets(timeline)
            await resolve_audio_assets(timeline)
            composite_timeline(timeline, source_video_path, resolved_assets, output_path)
        except Exception as exc:
            logger.exception("Render failed for project=%s", project_id)
            await _mark_project_status(project_id, ProjectStatus.FAILED, error_message=str(exc))
            raise

        logger.info("Render complete for project=%s -> %s", project_id, output_path)
        await _mark_project_status(project_id, ProjectStatus.RENDERED, rendered_path=output_path)
        return output_path

    return asyncio.run(_run())
