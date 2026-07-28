"""
Agent 3: Visual Director.

Job: for each segment, decide WHICH KIND of visual fits (real B-roll,
a stat callout, a generated image, an on-screen demo, or a PIP "bubble"
cutaway) — but never invent a specific asset name, filename, or URL. It
only ever describes what it wants in generic, real-world terms; the
actual asset resolution happens later by real engines (Stock Footage,
Image Generation, etc.) or gets caught by the Validator if something
still slips through.

This agent is deliberately given a closed list of what's real:
  - the actual UI template filenames that exist on disk
  - a real browser-demo URL, ONLY if one has been configured
If no real URL is configured, "browser" is not offered as an option at
all — removing the single biggest source of invented-URL bugs.

Crucially, this agent also decides INSERT TIMING: a B-roll/graphic
overlay should be a short cutaway (a second or two) within a segment,
not the segment's entire duration — real editing cuts away briefly and
then returns to the speaker's face. Without this, every visual event
ends up covering its whole segment, which reads as sluggish rather than
punchy.

If a Creative Director treatment is provided, it's included as extra
context so this agent executes a specific creative vision instead of
deciding in a vacuum.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment, VisualEvent, VisualSource

logger = logging.getLogger(__name__)

DEFAULT_INSERT_DURATION = 1.8  # seconds — sane fallback if the agent omits timing
MIN_INSERT_DURATION = 0.6
MAX_INSERT_FRACTION = 0.85  # never let an insert eat almost the whole segment


def _build_system_prompt(real_templates: list[str], browser_url: str | None) -> str:
    sources = [
        "stock_footage", "motion_graphics", "image_generation",
        "ui_template", "original_footage", "pip_overlay",
    ]
    browser_note = ""
    if browser_url:
        sources.insert(0, "browser")
        browser_note = f'\n"browser" events MUST use exactly this URL as asset_ref: {browser_url}\n'

    templates_note = ", ".join(real_templates) if real_templates else "stat_card"

    return f"""\
You are the Visual Director for a short-form video. For each segment,
decide what kind of visual (if any) supports it. You may use these
source types ONLY: {", ".join(sources)}.
{browser_note}
For "ui_template" events, asset_ref MUST be one of these exact existing
template names (do not invent new ones): {templates_note}

For "stock_footage", "image_generation", and "pip_overlay" events, do NOT
set asset_ref at all — instead write a generic, real-world "prompt"
describing the visual.

CRITICAL constraint on "prompt" for stock_footage and pip_overlay: these
get matched against a REAL stock footage library search (Pexels-style).
That search can only find generic, real-world scenes that actually exist
as filmed footage — it CANNOT find a specific fictional document, a
specific UI mockup with invented text/labels, or a screenshot of a
"template titled X". Prompts like "invoice stamped $7,500 PAID" or
"UI template titled 'Bottleneck Map' with three gold checklist rows"
will fail to match anything real and return irrelevant footage.

Instead, describe the generic REAL-WORLD equivalent of what you're going
for — e.g. instead of "invoice stamped $7,500 PAID", write "hands
signing a printed invoice on a desk"; instead of "UI template titled
'Bottleneck Map'", write "laptop screen showing a colorful project
dashboard" or "person typing on a laptop with a spreadsheet open". Keep
every prompt to something a real stock footage search would plausibly
have footage of. "image_generation" prompts are the ONE exception where
specific invented visuals (like a custom UI mockup or graphic) are fine,
since that gets rendered fresh rather than searched for.

"pip_overlay" is a picture-in-picture "bubble" cutaway: the speaker's own
face shrinks into a small circle (bottom-right corner) while the B-roll
described in "prompt" fills the rest of the frame behind it, then the
video pops back to full-frame speaker afterward. Use this when you want
to show something on screen WITHOUT fully cutting away from the speaker.

IMPORTANT for pip_overlay specifically: if you want the bubble effect to
span multiple consecutive segments (e.g. covering a longer explanation),
give EACH segment its own pip_overlay event that covers that segment's
ENTIRE duration (insert_offset near 0, insert_duration close to the full
segment length) — do NOT give it only a short 1-2 second window within
each segment. A pip_overlay that only covers a fraction of the segment
will cause the speaker's full-frame face to visibly pop back in in the
middle of segments where you wanted the bubble to stay, which reads as
a jarring flicker rather than a smooth continuous effect.

For "motion_graphics" events, keep them SHORT — never more than 4
seconds — and only for a specific stat, label, or callout tied to one
moment. Never describe the overall caption style of the video.

TIMING — this matters a lot for pacing: every visual event (except
"original_footage" and "pip_overlay") is a brief CUTAWAY within the
segment, not the whole segment. Provide:
  - "insert_offset": seconds from the START of the segment where the
    cutaway begins (usually 0.2-1.0s in, so the speaker's face is seen
    briefly first)
  - "insert_duration": how long the cutaway lasts, in seconds
    (typically 1.0-2.5s for B-roll/images/UI, up to 4s for motion
    graphics). Never span the entire segment for these cutaway types.
For "pip_overlay", as noted above, insert_offset should be near 0 and
insert_duration should cover the segment's full length instead.

Also avoid stacking two full-frame cutaways (stock_footage,
motion_graphics, image_generation, ui_template, browser) back-to-back
with little or no gap between them — that reads as flickery rather than
punchy. Leave the speaker's face visible for at least a second or two
between separate cutaways.

Return EXACTLY this JSON shape, nothing else:
{{
  "visual_events": [
    {{"segment_id": "seg_0", "source": "stock_footage", "prompt": "...",
      "camera_move": "none", "z_index": 0,
      "insert_offset": 0.4, "insert_duration": 1.6}}
  ]
}}
Not every segment needs a visual event — use your judgment; original
footage (segment id present but no event) is a perfectly good default.
"""


def _resolve_insert_window(
    segment: Segment, raw_offset: float | None, raw_duration: float | None
) -> tuple[float, float]:
    """Turn the agent's requested offset/duration into a real, clamped
    (start, end) window that always stays within the segment's bounds
    and never eats the whole segment, even if the agent omits or
    misjudges the timing fields."""
    segment_length = max(segment.end - segment.start, 0.1)
    max_duration = max(segment_length * MAX_INSERT_FRACTION, MIN_INSERT_DURATION)

    duration = raw_duration if raw_duration and raw_duration > 0 else DEFAULT_INSERT_DURATION
    duration = max(MIN_INSERT_DURATION, min(duration, max_duration))

    offset = raw_offset if raw_offset is not None and raw_offset >= 0 else 0.3
    offset = min(offset, max(segment_length - duration, 0.0))

    start = segment.start + offset
    end = min(start + duration, segment.end)
    return start, end


def _resolve_pip_window(segment: Segment) -> tuple[float, float]:
    """PIP overlay events always span the segment's FULL duration rather
    than a short cutaway window — this is what keeps a multi-segment PIP
    effect continuous instead of snapping in and out mid-effect."""
    return segment.start, segment.end


def run_visual_director(
    segments: list[Segment],
    pacing_map: dict[str, dict],
    real_templates: list[str],
    browser_url: str | None,
    treatment: str | None = None,
) -> list[VisualEvent]:
    """Returns a list of VisualEvent. Falls back to an empty list (i.e.
    just the original talking-head footage, no overlays) if the call
    fails — a plain video is always better than a crashed pipeline."""
    settings = get_settings()

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        segments_json = json.dumps(
            [
                {
                    "id": s.id, "start": s.start, "end": s.end, "text": s.text,
                    "is_hook": s.is_hook, "is_pattern_interrupt": s.is_pattern_interrupt,
                    "energy": pacing_map.get(s.id, {}).get("energy", "medium"),
                }
                for s in segments
            ],
            indent=2,
        )

        user_content = f"Segments:\n{segments_json}"
        if treatment:
            user_content = (
                f"Creative Director's treatment for this video:\n{treatment}\n\n{user_content}"
            )

        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _build_system_prompt(real_templates, browser_url)},
                {"role": "user", "content": user_content},
            ],
        )
        data = json.loads(response.choices[0].message.content)

        valid_ids = {s.id for s in segments}
        events: list[VisualEvent] = []
        for raw in data.get("visual_events", []):
            seg_id = raw.get("segment_id")
            if seg_id not in valid_ids:
                continue
            segment = next(s for s in segments if s.id == seg_id)

            source = raw.get("source", "original_footage")
            if source == VisualSource.ORIGINAL_FOOTAGE:
                continue  # nothing to build an overlay for

            if source == VisualSource.PIP_OVERLAY:
                start, end = _resolve_pip_window(segment)
            else:
                start, end = _resolve_insert_window(
                    segment, raw.get("insert_offset"), raw.get("insert_duration")
                )

            try:
                events.append(
                    VisualEvent(
                        segment_id=seg_id,
                        source=source,
                        start=start,
                        end=end,
                        prompt=raw.get("prompt"),
                        asset_ref=raw.get("asset_ref"),
                        camera_move=raw.get(
                            "camera_move", pacing_map.get(seg_id, {}).get("camera_move", "none")
                        ),
                        z_index=raw.get("z_index", 0),
                    )
                )
            except Exception:
                logger.warning("Skipping malformed visual_event for segment=%s", seg_id)

        logger.info("Visual Director: produced %d visual events", len(events))
        return events

    except Exception:
        logger.exception("Visual Director failed — proceeding with no visual overlays")
        return []
