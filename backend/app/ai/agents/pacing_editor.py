"""
Agent 2: Pacing / Editor.

Job: decide the *feel* of each segment — how much energy it carries and
what camera move (if any) suits it. This feeds the Visual Director and
Sound Designer so their choices are consistent with the edit's rhythm,
without either of them needing to reason about pacing themselves.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Pacing Editor for a short-form video. For each segment,
decide two things ONLY:
  - "energy": one of "low", "medium", "high" — how punchy/urgent this
    moment should feel
  - "camera_move": one of "none", "zoom_in", "zoom_out", "pan_left",
    "pan_right", "shake" — a subtle camera move that fits the energy
    (high energy can justify a quick zoom or shake; low energy usually
    stays "none")

You do not decide what's shown on screen or what sound plays — only the
pacing/camera feel of each moment.

Return EXACTLY this JSON shape, nothing else:
{
  "segments": [
    {"id": "seg_0", "energy": "high", "camera_move": "zoom_in"}
  ]
}
Every segment id from the input must appear exactly once.
"""


def run_pacing_editor(segments: list[Segment]) -> dict[str, dict]:
    """Returns {segment_id: {"energy": ..., "camera_move": ...}}. Falls
    back to a safe default (medium energy, no camera move) per segment
    if the call fails."""
    settings = get_settings()
    default = {"energy": "medium", "camera_move": "none"}
    fallback = {s.id: dict(default) for s in segments}

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        transcript_json = json.dumps(
            [{"id": s.id, "text": s.text, "is_hook": s.is_hook,
              "is_pattern_interrupt": s.is_pattern_interrupt} for s in segments],
            indent=2,
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Segments:\n{transcript_json}"},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        result = dict(fallback)
        for seg in data.get("segments", []):
            sid = seg.get("id")
            if sid in result:
                result[sid] = {
                    "energy": seg.get("energy", "medium"),
                    "camera_move": seg.get("camera_move", "none"),
                }
        logger.info("Pacing Editor: assigned pacing for %d segments", len(result))
        return result

    except Exception:
        logger.exception("Pacing Editor failed — using default medium/none pacing for all segments")
        return fallback
