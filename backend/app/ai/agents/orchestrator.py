"""
Multi-Agent Orchestrator.

Runs the full agent pipeline in sequence, each seeing only the context
it needs:

  0. Creative Director     -> live-trend-grounded creative treatment
  1. Script Analyst        -> hooks, pattern interrupts, CTA
  2. Pacing/Editor         -> per-segment energy + camera move
  3a. Visual Director + Motion Graphics Designer (layout="full")
      -> which visual per moment, generic real-world terms only
  3b. Scene Designer (layout="split_demo")
      -> structured Konva scene per segment for the top-half graphic
  4. Sound Designer        -> music mood + SFX moments

Caption styling is NOT an agent — it's a rule-based lookup, since which
font/color a style preset uses is a fixed design decision.

Each agent degrades gracefully on its own — if one fails, the pipeline
still produces a Timeline with sensible defaults for that agent's piece.
The result still passes through validate_and_fix_timeline() afterward as
a final safety net.
"""
import logging

from app.ai.agents.caption_styles import get_caption_style
from app.ai.agents.creative_director import run_creative_director
from app.ai.agents.motion_graphics_designer import run_motion_graphics_designer
from app.ai.agents.pacing_editor import run_pacing_editor
from app.ai.agents.scene_designer import run_scene_designer
from app.ai.agents.script_analyst import run_script_analyst
from app.ai.agents.sound_designer import run_sound_designer
from app.ai.agents.visual_director import run_visual_director
from app.ai.validator import get_real_ui_template_names
from app.core.config import get_settings
from app.models.timeline import Segment, Timeline

logger = logging.getLogger(__name__)


def run_multi_agent_director(
    segments: list[Segment],
    project_id: str,
    style_preset: str,
    duration: float,
    caption_overrides: dict | None = None,
    layout: str = "full",
) -> tuple[Timeline, str]:
    settings = get_settings()

    logger.info(
        "Starting multi-agent Timeline generation for project=%s style=%s layout=%s segments=%d",
        project_id, style_preset, layout, len(segments),
    )

    treatment = run_creative_director(segments, style_preset)
    logger.info("Creative Director treatment for project=%s:\n%s", project_id, treatment)

    segments, cta_events = run_script_analyst(segments, style_preset)
    pacing_map = run_pacing_editor(segments)

    visual_events = []
    scene_events = []

    if layout == "split_demo":
        scene_events = run_scene_designer(segments, treatment)
    else:
        real_templates = sorted(
            name.removesuffix(".html") for name in get_real_ui_template_names()
        )
        visual_events = run_visual_director(
            segments, pacing_map, real_templates, settings.browser_demo_url, treatment
        )
        visual_events = run_motion_graphics_designer(visual_events)

    audio_events = run_sound_designer(segments, duration)

    caption_style = get_caption_style(style_preset)
    if layout == "split_demo":
        # Split layout defaults to progressive-reveal, safe-zone-positioned
        # captions unless the user's own overrides explicitly say otherwise —
        # this is the pairing that actually makes sense for this layout.
        split_defaults = {"animation": "progressive_reveal", "position": "split_line"}
        caption_style = caption_style.model_copy(update=split_defaults)
    if caption_overrides:
        caption_style = caption_style.model_copy(update=caption_overrides)

    timeline = Timeline(
        project_id=project_id,
        style_preset=style_preset,
        duration=duration,
        layout=layout,
        caption_style=caption_style,
        segments=segments,
        visual_events=visual_events,
        scene_events=scene_events,
        audio_events=audio_events,
        cta_events=cta_events,
    )

    logger.info(
        "Multi-agent Timeline complete: %d visual events, %d scene events, %d audio events, %d CTAs",
        len(timeline.visual_events), len(timeline.scene_events),
        len(timeline.audio_events), len(timeline.cta_events),
    )
    return timeline, treatment
