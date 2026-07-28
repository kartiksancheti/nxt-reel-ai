"""
Agent 4: Motion Graphics Designer.

Job: given only the motion_graphics events the Visual Director already
placed, write the actual short on-screen text (a stat, a label, a
callout) — never more than a handful of words, never a description of
the whole video's caption style. Operating on a narrow, pre-filtered
subset of events (instead of the whole timeline) is what keeps this
agent from drifting into inventing something unrelated.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import VisualEvent, VisualSource

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Motion Graphics Designer for short-form video. You receive a
list of moments that need a short on-screen graphic (a stat, a label, a
callout, a badge). For each one, write the EXACT text that should appear
on screen.

Rules:
  - Maximum 6 words per graphic. Shorter is better.
  - Never describe a caption style, animation technique, or video-wide
    concept — only the literal words to display (e.g. "92% skip this"
    is good; "kinetic captions with bold keywords" is NOT allowed).
  - Keep it punchy and specific to that one moment.

Return EXACTLY this JSON shape, nothing else:
{
  "graphics": [
    {"segment_id": "seg_0", "text": "..."}
  ]
}
"""


def run_motion_graphics_designer(visual_events: list[VisualEvent]) -> list[VisualEvent]:
    """Rewrites the `prompt` field of every motion_graphics event to a
    short, concrete on-screen text. Non-motion-graphics events pass
    through untouched. Falls back to leaving the original prompt as-is
    (already length-capped elsewhere) if the call fails."""
    motion_events = [e for e in visual_events if e.source == VisualSource.MOTION_GRAPHICS]
    if not motion_events:
        return visual_events

    settings = get_settings()
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        events_json = json.dumps(
            [{"segment_id": e.segment_id, "original_idea": e.prompt} for e in motion_events],
            indent=2,
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Moments needing graphics:\n{events_json}"},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        text_by_segment = {g["segment_id"]: g["text"] for g in data.get("graphics", []) if g.get("text")}

        updated = 0
        for event in visual_events:
            if event.source == VisualSource.MOTION_GRAPHICS and event.segment_id in text_by_segment:
                event.prompt = text_by_segment[event.segment_id]
                updated += 1

        logger.info("Motion Graphics Designer: refined %d/%d graphics", updated, len(motion_events))
        return visual_events

    except Exception:
        logger.exception(
            "Motion Graphics Designer failed — leaving original graphic text as-is"
        )
        return visual_events
