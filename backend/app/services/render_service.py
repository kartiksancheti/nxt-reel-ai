"""
Render Engine.

The final, "dumb" executor. By the time a Timeline reaches this module,
every creative decision has already been made — this only ever resolves
visual/scene events through the right engine, then composites everything
with MoviePy/FFmpeg exactly as instructed. No creative judgment happens
here, by design.
"""
import logging
from pathlib import Path

import numpy as np
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
from app.engines.konva_scene_engine import KonvaSceneEngine
from app.engines.motion_graphics_engine import MotionGraphicsEngine
from app.engines.stock_engine import StockFootageEngine
from app.engines.ui_template_engine import UITemplateEngine
from app.models.timeline import CameraMove, Segment, Timeline, VisualSource

logger = logging.getLogger(__name__)

ENGINE_MAP = {
    VisualSource.BROWSER: BrowserEngine(),
    VisualSource.STOCK_FOOTAGE: StockFootageEngine(),
    VisualSource.MOTION_GRAPHICS: MotionGraphicsEngine(),
    VisualSource.IMAGE_GENERATION: ImageGenerationEngine(),
    VisualSource.UI_TEMPLATE: UITemplateEngine(),
    VisualSource.PIP_OVERLAY: StockFootageEngine(),
}

TARGET_RESOLUTION = (1080, 1920)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
CUT_GAP_SECONDS = 0.06

MERGE_GAP_SECONDS = 0.25
PIP_MERGE_GAP_SECONDS = 1.5
MIN_CUTAWAY_GAP_SECONDS = 1.0

CUTAWAY_SOURCES = {
    VisualSource.STOCK_FOOTAGE,
    VisualSource.MOTION_GRAPHICS,
    VisualSource.IMAGE_GENERATION,
    VisualSource.UI_TEMPLATE,
    VisualSource.BROWSER,
}

PIP_DIAMETER = 460
PIP_MARGIN = 40

# Y-coordinates for exact caption placement, used by the progressive-
# reveal renderer. "safe_top" sits well above where Instagram Reels' own
# UI (bottom caption/username bar, right-side icons) would ever overlap.
# "split_line" sits just above the halfway point, for the split_demo
# layout where captions bridge the top/bottom halves.
PROGRESSIVE_Y_MAP = {
    "top": 180,
    "center": 860,
    "bottom": 1500,
    "safe_top": int(TARGET_RESOLUTION[1] * 0.20),
    "split_line": 900,
}


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


async def resolve_scene_assets(timeline: Timeline) -> dict[str, str]:
    """Resolves every SceneEvent (split_demo layout only) into a rendered
    Konva video clip. No-op for the "full" layout."""
    if timeline.layout != "split_demo" or not timeline.scene_events:
        return {}
    engine = KonvaSceneEngine()
    resolved: dict[str, str] = {}
    for scene in timeline.scene_events:
        try:
            path = await engine.resolve_scene(scene, timeline.project_id)
            resolved[scene.segment_id] = path
        except Exception:
            logger.exception(
                "Failed to resolve Konva scene for segment=%s — top half will be blank for this moment",
                scene.segment_id,
            )
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


def _fit_to_half(clip, half: str = "bottom"):
    """Resize + center-crop a clip to fill exactly the top or bottom HALF
    of the target frame (used by the split_demo layout)."""
    target_w = TARGET_RESOLUTION[0]
    target_h = TARGET_RESOLUTION[1] // 2
    clip_ratio = clip.w / clip.h
    target_ratio = target_w / target_h

    if clip_ratio > target_ratio:
        resized = clip.resize(height=target_h)
        resized = resized.crop(x_center=resized.w / 2, width=target_w)
    else:
        resized = clip.resize(width=target_w)
        resized = resized.crop(y_center=resized.h / 2, height=target_h)

    y = target_h if half == "bottom" else 0
    return resized.set_position((0, y))


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
    actually speaking."""

    def __init__(self, timeline: Timeline):
        segments: list[Segment] = sorted(timeline.segments, key=lambda s: s.start)
        self.cut_ranges: list[tuple[float, float]] = []
        self.shift_by_segment: dict[str, float] = {}
        self.new_start_by_segment: dict[str, float] = {}

        cursor = 0.0
        range_start: float | None = None
        range_end: float | None = None
        pending: list[Segment] = []

        def flush() -> None:
            nonlocal cursor, range_start, range_end, pending
            if range_start is None:
                return
            self.cut_ranges.append((range_start, range_end))
            for seg in pending:
                shift = cursor - range_start
                self.shift_by_segment[seg.id] = shift
                self.new_start_by_segment[seg.id] = seg.start + shift
            cursor += (range_end - range_start) + CUT_GAP_SECONDS
            pending = []
            range_start = None
            range_end = None

        for seg in segments:
            if range_start is None:
                range_start, range_end = seg.start, seg.end
                pending = [seg]
            elif seg.start - range_end <= MERGE_GAP_SECONDS:
                range_end = max(range_end, seg.end)
                pending.append(seg)
            else:
                flush()
                range_start, range_end = seg.start, seg.end
                pending = [seg]
        flush()
        self.total_duration = max(cursor - CUT_GAP_SECONDS, 0.1)

    def shift_for_segment(self, segment_id: str) -> float:
        return self.shift_by_segment.get(segment_id, 0.0)

    def new_start_for_segment(self, segment_id: str) -> float | None:
        return self.new_start_by_segment.get(segment_id)


def _build_cut_base_clip(source_video_path: str, cut_plan: CutPlan, fit_full: bool = True):
    """Concatenate only the speaking ranges from the source footage, back
    to back. If fit_full is False, returns the raw concatenated clip
    without fitting to the full frame — used by the split_demo layout,
    which fits it to the bottom HALF instead."""
    source = VideoFileClip(source_video_path)
    subclips = []
    for start, end in cut_plan.cut_ranges:
        end = min(end, source.duration)
        start = min(start, end)
        if end - start <= 0:
            continue
        subclips.append(source.subclip(start, end))
    if not subclips:
        cut = source
    else:
        cut = concatenate_videoclips(subclips, method="compose")
    return _fit_to_target(cut) if fit_full else cut


def _make_circular_mask_clip(diameter: int, duration: float):
    size = diameter
    y, x = np.ogrid[:size, :size]
    center = size / 2
    dist = np.sqrt((x - center) ** 2 + (y - center) ** 2)
    mask_array = (dist <= center).astype(float)
    return ImageClip(mask_array, ismask=True).set_duration(duration)


def _build_pip_bubble_overlay(source_clip, event):
    seg_start = max(event.start, 0.0)
    seg_end = min(event.end, source_clip.duration)
    if seg_end <= seg_start:
        return None

    face = source_clip.subclip(seg_start, seg_end).without_audio()
    face = face.resize(height=PIP_DIAMETER)
    if face.w != face.h:
        side = min(face.w, face.h)
        face = face.crop(x_center=face.w / 2, y_center=face.h / 2, width=side, height=side)

    mask = _make_circular_mask_clip(face.w, face.duration)
    face = face.set_mask(mask)

    pos_x = TARGET_RESOLUTION[0] - face.w - PIP_MARGIN
    pos_y = TARGET_RESOLUTION[1] - face.h - PIP_MARGIN
    return face.set_position((pos_x, pos_y))


def _prepare_visual_events(
    timeline: Timeline, resolved_assets: dict[str, str], cut_plan: CutPlan
) -> list[tuple]:
    candidates = [e for e in timeline.visual_events if e.segment_id in resolved_assets]
    candidates.sort(key=lambda e: e.start)

    merged: list = []
    asset_for: dict[int, str] = {}
    i = 0
    while i < len(candidates):
        event = candidates[i]
        asset_path = resolved_assets[event.segment_id]
        if event.source == VisualSource.PIP_OVERLAY:
            base_shift = cut_plan.shift_for_segment(event.segment_id)
            merged_start, merged_end = event.start, event.end
            j = i + 1
            while j < len(candidates):
                nxt = candidates[j]
                if (
                    nxt.source == VisualSource.PIP_OVERLAY
                    and cut_plan.shift_for_segment(nxt.segment_id) == base_shift
                    and nxt.start - merged_end <= PIP_MERGE_GAP_SECONDS
                ):
                    merged_end = max(merged_end, nxt.end)
                    j += 1
                else:
                    break
            new_event = event.model_copy(update={"start": merged_start, "end": merged_end})
            merged.append(new_event)
            asset_for[id(new_event)] = asset_path
            i = j
        else:
            merged.append(event)
            asset_for[id(event)] = asset_path
            i += 1

    spaced: list = []
    last_cutaway_end: float | None = None
    for event in merged:
        if event.source in CUTAWAY_SOURCES:
            if last_cutaway_end is not None and event.start - last_cutaway_end < MIN_CUTAWAY_GAP_SECONDS:
                logger.info(
                    "Dropping cutaway on segment=%s (starts %.2fs after previous cutaway ended) "
                    "— too close together, would read as flicker",
                    event.segment_id, event.start - last_cutaway_end,
                )
                continue
            last_cutaway_end = event.end
        spaced.append(event)

    return [(e, asset_for[id(e)]) for e in spaced]


def _build_visual_overlay_clips(
    timeline: Timeline,
    resolved_assets: dict[str, str],
    cut_plan: CutPlan,
    source_video_path: str | None = None,
) -> list:
    prepared = _prepare_visual_events(timeline, resolved_assets, cut_plan)
    prepared.sort(key=lambda pair: pair[0].z_index)

    clips = []
    pip_source_clip = None
    for event, asset_path in prepared:
        duration = max(event.end - event.start, 0.1)
        if event.source == VisualSource.MOTION_GRAPHICS:
            duration = min(duration, 5.0)
        shift = cut_plan.shift_for_segment(event.segment_id)
        new_start = max(event.start + shift, 0.0)
        try:
            clip = _load_visual_clip(asset_path, duration)
            clip = _fit_to_target(clip)
            clip = _apply_camera_move(clip, event.camera_move, duration)
            clip = clip.set_start(new_start).set_duration(duration)
            clips.append(clip)

            if event.source == VisualSource.PIP_OVERLAY and source_video_path:
                if pip_source_clip is None:
                    pip_source_clip = VideoFileClip(source_video_path)
                bubble = _build_pip_bubble_overlay(pip_source_clip, event)
                if bubble is not None:
                    clips.append(bubble.set_start(new_start))
        except Exception:
            logger.exception(
                "Failed to composite visual asset for segment=%s (%s) — skipping",
                event.segment_id, asset_path,
            )
    return clips


def _build_split_layout_clips(
    timeline: Timeline, scene_assets: dict[str, str], cut_plan: CutPlan
) -> list:
    """Top-half Konva scene clips for the split_demo layout, one per
    SceneEvent, positioned to fill exactly the top half of the frame for
    that segment's full (shifted) duration."""
    clips = []
    for scene in timeline.scene_events:
        path = scene_assets.get(scene.segment_id)
        if not path:
            continue
        duration = max(scene.end - scene.start, 0.1)
        shift = cut_plan.shift_for_segment(scene.segment_id)
        new_start = max(scene.start + shift, 0.0)
        try:
            clip = VideoFileClip(path).without_audio()
            if clip.duration < duration:
                clip = clip.fx(vfx.loop, duration=duration)
            else:
                clip = clip.subclip(0, duration)
            clip = _fit_to_half(clip, half="top")
            clip = clip.set_start(new_start).set_duration(duration)
            clips.append(clip)
        except Exception:
            logger.exception(
                "Failed to composite Konva scene for segment=%s (%s) — top half blank for this moment",
                scene.segment_id, path,
            )
    return clips


def _motion_graphics_windows(timeline: Timeline, cut_plan: CutPlan) -> list[tuple[float, float]]:
    windows = []
    for event in timeline.visual_events:
        if event.source != VisualSource.MOTION_GRAPHICS:
            continue
        shift = cut_plan.shift_for_segment(event.segment_id)
        windows.append((event.start + shift, event.end + shift))
    return windows


def _cta_windows(timeline: Timeline, cut_plan: CutPlan) -> list[tuple[float, float]]:
    """Time windows where a CTA overlay is on screen. Running word
    captions are suppressed during these windows too — same reasoning
    as motion graphics: two competing text elements on screen at once
    reads as a bug, not a design choice."""
    windows = []
    for cta in timeline.cta_events:
        shift = cut_plan.shift_for_segment(cta.segment_id)
        windows.append((cta.start + shift, cta.end + shift))
    return windows


def _in_any_window(t: float, windows: list[tuple[float, float]]) -> bool:
    return any(start <= t < end for start, end in windows)


def _build_progressive_reveal_clips(timeline: Timeline, cut_plan: CutPlan) -> list:
    """Whole-sentence captions that build up word-by-word — all words
    spoken so far stay visible on one line, and the word currently being
    spoken is highlighted. Positioning is pixel-accurate: each
    increment's width is measured directly from MoviePy's own rendered
    TextClip."""
    style = timeline.caption_style
    clips = []
    y = PROGRESSIVE_Y_MAP.get(style.position, PROGRESSIVE_Y_MAP["safe_top"])
    suppress_windows = _motion_graphics_windows(timeline, cut_plan) + _cta_windows(timeline, cut_plan)

    for segment in timeline.segments:
        words = segment.words
        if not words or not segment.text.strip():
            continue
        new_seg_start = cut_plan.new_start_for_segment(segment.id)
        if new_seg_start is None:
            continue
        shift = new_seg_start - segment.start

        for i, word in enumerate(words):
            w_start = max(word.start + shift, 0.0)
            if _in_any_window(w_start, suppress_windows):
                continue
            w_end_orig = words[i + 1].start if i + 1 < len(words) else segment.end
            w_duration = max((w_end_orig + shift) - w_start, 0.08)

            prefix_words = [w.text for w in words[:i] if w.text.strip()]
            revealed_text = " ".join(prefix_words + [word.text])

            try:
                revealed_clip = TextClip(
                    revealed_text,
                    fontsize=style.size,
                    color=style.color,
                    font=style.font,
                    method="label",
                    stroke_color="black",
                    stroke_width=2,
                )
                block_w = revealed_clip.w
                base_x = max((TARGET_RESOLUTION[0] - block_w) / 2, 0)
                revealed_clip = (
                    revealed_clip.set_position((base_x, y)).set_start(w_start).set_duration(w_duration)
                )
                clips.append(revealed_clip)

                if prefix_words:
                    prefix_with_space_clip = TextClip(
                        " ".join(prefix_words) + " ",
                        fontsize=style.size,
                        color=style.color,
                        font=style.font,
                        method="label",
                    )
                    current_x_offset = prefix_with_space_clip.w
                    prefix_with_space_clip.close()
                else:
                    current_x_offset = 0

                highlight_clip = (
                    TextClip(
                        word.text,
                        fontsize=style.size,
                        color=style.highlight_color,
                        font=style.font,
                        method="label",
                        stroke_color="black",
                        stroke_width=2,
                    )
                    .set_position((base_x + current_x_offset, y))
                    .set_start(w_start)
                    .set_duration(w_duration)
                )
                clips.append(highlight_clip)
            except Exception:
                logger.exception(
                    "Failed to render progressive-reveal caption for word '%s' in segment=%s — skipping",
                    word.text, segment.id,
                )

    logger.info("Progressive-reveal captions: built %d clips at y=%d", len(clips), y)
    return clips


def _build_kinetic_caption_clips(timeline: Timeline, cut_plan: CutPlan) -> list:
    if timeline.caption_style.animation == "progressive_reveal":
        return _build_progressive_reveal_clips(timeline, cut_plan)

    style = timeline.caption_style
    clips = []
    y_position = {
        "top": ("center", 200),
        "center": "center",
        "bottom": ("center", "bottom"),
        "safe_top": ("center", int(TARGET_RESOLUTION[1] * 0.20)),
        "split_line": ("center", 900),
    }.get(style.position, "center")
    suppress_windows = _motion_graphics_windows(timeline, cut_plan) + _cta_windows(timeline, cut_plan)

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
                clamped_end = min(word.end, segment.end)
                w_duration = max(clamped_end - word.start, 0.08)
                if _in_any_window(w_start, suppress_windows):
                    continue
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
            words = segment.text.split()
            if not words:
                continue
            per_word = max(segment.end - segment.start, 0.1) / len(words)
            for i, word_text in enumerate(words):
                w_start = max(segment.start + shift + i * per_word, 0.0)
                w_duration = max(per_word, 0.08)
                if _in_any_window(w_start, suppress_windows):
                    continue
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
    layers = []
    if base_audio is not None:
        layers.append(base_audio.volumex(1.4))

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
    scene_assets: dict[str, str],
    output_path: str,
) -> str:
    logger.info(
        "Compositing timeline for project=%s -> %s (layout=%s, %d visual, %d scene, %d audio, %d cta events)",
        timeline.project_id, output_path, timeline.layout,
        len(timeline.visual_events), len(timeline.scene_events),
        len(timeline.audio_events), len(timeline.cta_events),
    )

    cut_plan = CutPlan(timeline)

    if timeline.layout == "split_demo":
        raw_base = _build_cut_base_clip(source_video_path, cut_plan, fit_full=False)
        raw_base = raw_base.set_duration(min(raw_base.duration, cut_plan.total_duration or raw_base.duration))
        base = _fit_to_half(raw_base, half="bottom").set_duration(raw_base.duration)
        layers = [base]
        layers.extend(_build_split_layout_clips(timeline, scene_assets, cut_plan))
    else:
        base = _build_cut_base_clip(source_video_path, cut_plan)
        base = base.set_duration(min(base.duration, cut_plan.total_duration or base.duration))
        layers = [base]
        layers.extend(_build_visual_overlay_clips(timeline, resolved_assets, cut_plan, source_video_path))

    layers.extend(_build_kinetic_caption_clips(timeline, cut_plan))
    layers.extend(_build_cta_clips(timeline, cut_plan))

    final = CompositeVideoClip(layers, size=TARGET_RESOLUTION).set_duration(base.duration)

    audio_track = _build_audio_track(timeline, base.audio)
    if audio_track is not None:
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
            scene_assets = await resolve_scene_assets(timeline)
            await resolve_audio_assets(timeline)
            composite_timeline(timeline, source_video_path, resolved_assets, scene_assets, output_path)
        except Exception as exc:
            logger.exception("Render failed for project=%s", project_id)
            await _mark_project_status(project_id, ProjectStatus.FAILED, error_message=str(exc))
            raise

        logger.info("Render complete for project=%s -> %s", project_id, output_path)
        await _mark_project_status(project_id, ProjectStatus.RENDERED, rendered_path=output_path)
        return output_path

    return asyncio.run(_run())
