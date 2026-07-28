"""
AI Director.

Core philosophy of this project: "AI decides everything; renderer only
executes." This module is where that decision-making actually happens.

Given a transcript + style preset, the Director decides:
  - which sentences are hooks / pattern interrupts
  - where B-roll, motion graphics, browser recordings should appear
  - where zooms/camera moves land
  - music, SFX, and CTA placement

It never touches pixels or renders anything — it only ever outputs a
Timeline (see app/models/timeline.py), which the Render Engine executes
literally and without judgment.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment, Timeline

logger = logging.getLogger(__name__)

DIRECTOR_SYSTEM_PROMPT = """\
You are the AI Creative Director for a short-form video editing pipeline.
You receive a timestamped transcript of a talking-head video and a style
preset. You decide the full edit: hooks, pattern interrupts, B-roll
placement, motion graphics, browser recordings, zooms/camera moves, music,
sound effects, and a call-to-action.

You MUST return a single JSON object using EXACTLY these field names —
do not invent alternate names, do not nest fields differently, do not omit
any required field:

{
  "segments": [
    {"id": "seg_0", "start": 0.0, "end": 2.0, "text": "...",
     "is_hook": true, "is_pattern_interrupt": false}
  ],
  "visual_events": [
    {"segment_id": "seg_0", "source": "stock_footage", "start": 0.0,
     "end": 2.0, "prompt": "city skyline at night", "asset_ref": null,
     "camera_move": "zoom_in", "z_index": 0}
  ],
  "audio_events": [
    {"kind": "music", "asset_ref": "upbeat_track_1", "start": 0.0,
     "end": 30.0, "volume_db": -6}
  ],
  "cta_events": [
    {"segment_id": "seg_9", "text": "Follow for more", "start": 25.2,
     "end": 27.0}
  ]
}

"source" must be one of: browser, stock_footage, motion_graphics,
image_generation, ui_template, original_footage.
"camera_move" must be one of: none, zoom_in, zoom_out, pan_left,
pan_right, shake.
"kind" (audio_events) must be one of: music, sfx.
Never include prose outside the JSON. Never use field names other than
the ones shown above.
"""

def build_director_prompt(segments: list[Segment], style_preset: str) -> str:
    transcript_json = json.dumps([s.model_dump() for s in segments], indent=2)
    return (
        f"Style preset: {style_preset}\n\n"
        f"Transcript segments (JSON):\n{transcript_json}\n\n"
        "Return a single JSON object for the `visual_events`, `audio_events`, "
        "and `cta_events` fields of the Timeline, plus updated `segments` with "
        "`is_hook` / `is_pattern_interrupt` flags set where appropriate."
    )


def run_director(
    segments: list[Segment],
    project_id: str,
    style_preset: str,
    duration: float,
) -> Timeline:
    """Call GPT-5 to produce the full creative decision set, then assemble
    it into a validated Timeline object."""
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    logger.info(
        "Running AI Director for project=%s style=%s segments=%d",
        project_id, style_preset, len(segments),
    )

    response = client.chat.completions.create(
        model=settings.openai_director_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT},
            {"role": "user", "content": build_director_prompt(segments, style_preset)},
        ],
    )

    decisions = json.loads(response.choices[0].message.content)

    timeline = Timeline(
        project_id=project_id,
        style_preset=style_preset,
        duration=duration,
        segments=decisions.get("segments", [s.model_dump() for s in segments]),
        visual_events=decisions.get("visual_events", []),
        audio_events=decisions.get("audio_events", []),
        cta_events=decisions.get("cta_events", []),
    )

    logger.info(
        "AI Director produced %d visual events, %d audio events, %d CTAs",
        len(timeline.visual_events), len(timeline.audio_events), len(timeline.cta_events),
    )
    return timeline
