"""
Multi-Agent Orchestrator.

Replaces the single do-everything GPT-5 call in app/ai/director.py with
5 narrow, specialized agents run in sequence, each seeing only the
context it needs:

  1. Script Analyst        -> hooks, pattern interrupts, CTA
  2. Pacing/Editor          -> per-segment energy + camera move
  3. Visual Director        -> which visual per moment (generic, real-world terms only)
  4. Motion Graphics Designer -> the actual short on-screen text
  5. Sound Designer         -> music mood + SFX moments (generic, searchable terms)

Caption styling is NOT an agent — it's a rule-based lookup (see
caption_styles.py), since which font/color a style preset uses is a
fixed design decision, not something worth an AI call.

Each agent degrades gracefully on its own (see individual modules) —
if one fails, the pipeline still produces a Timeline with sensible
defaults for that agent's piece, rather than crashing generate-timeline
entirely. The result still passes through validate_and_fix_timeline()
in the API route afterward as a final safety net.
"""
import logging

from app.ai.agents.caption_styles import get_caption_style
from app.ai.agents.motion_graphics_designer import run_motion_graphics_designer
from app.ai.agents.pacing_editor import run_pacing_editor
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
) -> Timeline:
    settings = get_settings()

    logger.info(
        "Starting multi-agent Timeline generation for project=%s style=%s segments=%d",
        project_id, style_preset, len(segments),
    )

    segments, cta_events = run_script_analyst(segments, style_preset)
    pacing_map = run_pacing_editor(segments)

    real_templates = sorted(
        name.removesuffix(".html") for name in get_real_ui_template_names()
    )
    visual_events = run_visual_director(
        segments, pacing_map, real_templates, settings.browser_demo_url
    )
    visual_events = run_motion_graphics_designer(visual_events)

    # re-attach the (possibly agent-produced) visual events onto the timeline
    # object below, keyed by their own start/end which the Visual Director
    # already set from each segment's timing.

    audio_events = run_sound_designer(segments, duration)
    caption_style = get_caption_style(style_preset)

    timeline = Timeline(
        project_id=project_id,
        style_preset=style_preset,
        duration=duration,
        caption_style=caption_style,
        segments=segments,
        visual_events=visual_events,
        audio_events=audio_events,
        cta_events=cta_events,
    )

    logger.info(
        "Multi-agent Timeline complete: %d visual events, %d audio events, %d CTAs",
        len(timeline.visual_events), len(timeline.audio_events), len(timeline.cta_events),
    )
    return timeline
