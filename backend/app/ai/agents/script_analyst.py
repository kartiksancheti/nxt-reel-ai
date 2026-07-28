"""
Agent 1: Script Analyst.

Job: pure narrative structure. Given only the transcript, decide which
sentences are the hook, which are pattern interrupts, and where a
call-to-action naturally belongs. This agent knows nothing about visuals,
cameras, or sound — that separation is the point: a narrower job is a
job GPT-5 can do reliably without inventing things outside its lane.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import CTAEvent, Segment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Script Analyst for short-form video. You receive a timestamped
transcript and decide ONLY narrative structure:
  - which segment(s) are the hook (the opening line(s) that earn attention)
  - which segment(s) are pattern interrupts (a tonal/topic shift that
    re-engages a drifting viewer)
  - where a single call-to-action (CTA) naturally belongs (usually near
    the end) and what short CTA text to show (e.g. "Follow for Day 2")

You do not decide anything about visuals, cameras, music, or sound effects.

Return EXACTLY this JSON shape, nothing else:
{
  "segments": [
    {"id": "seg_0", "is_hook": true, "is_pattern_interrupt": false}
  ],
  "cta": {"segment_id": "seg_9", "text": "Follow for Day 2"}
}
Every segment id from the input must appear exactly once in the output.
If no natural CTA moment exists, return "cta": null.
"""


def run_script_analyst(
    segments: list[Segment], style_preset: str
) -> tuple[list[Segment], list[CTAEvent]]:
    """Annotate segments with is_hook/is_pattern_interrupt, and produce
    at most one CTAEvent. Falls back to safe no-op defaults if the model
    call fails or returns something unusable — this agent's output is a
    nice-to-have annotation, not something worth crashing the pipeline
    over."""
    settings = get_settings()

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        transcript_json = json.dumps(
            [{"id": s.id, "start": s.start, "end": s.end, "text": s.text} for s in segments],
            indent=2,
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Style preset: {style_preset}\n\n"
                        f"Segments:\n{transcript_json}"
                    ),
                },
            ],
        )
        data = json.loads(response.choices[0].message.content)
        flags_by_id = {s["id"]: s for s in data.get("segments", [])}

        for seg in segments:
            flags = flags_by_id.get(seg.id, {})
            seg.is_hook = bool(flags.get("is_hook", False))
            seg.is_pattern_interrupt = bool(flags.get("is_pattern_interrupt", False))

        cta_events: list[CTAEvent] = []
        cta_data = data.get("cta")
        valid_ids = {s.id for s in segments}
        if cta_data and cta_data.get("segment_id") in valid_ids:
            target = next(s for s in segments if s.id == cta_data["segment_id"])
            cta_events.append(
                CTAEvent(
                    segment_id=target.id,
                    text=cta_data.get("text", "Follow for more"),
                    start=max(target.end - 2.0, target.start),
                    end=target.end,
                )
            )

        logger.info(
            "Script Analyst: %d hooks, %d pattern interrupts, cta=%s",
            sum(1 for s in segments if s.is_hook),
            sum(1 for s in segments if s.is_pattern_interrupt),
            bool(cta_events),
        )
        return segments, cta_events

    except Exception:
        logger.exception("Script Analyst failed — proceeding with no hook/CTA annotations")
        return segments, []
