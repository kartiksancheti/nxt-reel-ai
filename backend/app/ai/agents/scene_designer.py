"""
Agent 7: Scene Designer.

Job: for the "split_demo" layout only. Decides what goes in the TOP HALF
of the frame — a Konva.js graphic — for each segment, while the bottom
half stays the speaker's talking-head footage throughout.

Deliberately a closed, structured schema rather than free-form code: the
agent never writes JS/HTML/SVG itself, so there's no injection surface
and the Konva engine can render every scene deterministically.

Three scene types, ALL animated and visually rich — there is no plain
"static title + bullets" fallback anymore, since that reads as flat next
to the other two:
  - "diagram": labeled nodes (optionally connected) — for enumerated
    steps/options in the script.
  - "counter": a big animated stat with a sweeping progress ring — for
    a stat callout moment.
  - "dynamic": an animated gradient-background scene with drifting/
    pulsing accent shapes and a headline — for any moment that isn't a
    clean list or a single stat, so it never falls back to something
    static and plain.

The agent also decides, using its own judgment, whether consecutive
scenes should read as ONE continuous evolving graphic (reuse the same
accent_color/type) or as distinct scenes per moment — whichever fits.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment, SceneEvent, SceneElement

logger = logging.getLogger(__name__)

VALID_LAYOUT_TYPES = {"diagram", "counter", "dynamic", "simple"}  # "simple" kept for legacy scenes only

SYSTEM_PROMPT = """\
You are the Scene Designer for a split-screen short-form video: the TOP
HALF of the frame is an ANIMATED Konva.js graphic (NOT real video
footage, NOT a static slide — everything moves: gradients shift, shapes
pulse and glow, elements animate in), the BOTTOM HALF is the speaker's
talking-head footage, continuously, for the whole video. For each
segment, produce ONE scene for the top half.

You MUST pick "layout_type" from exactly these three — never anything
static or plain:

  - "diagram": the script ENUMERATES distinct steps or options (e.g.
    "lead entry, contract creation, follow-ups", any list of 2-4 named
    things). Provide "elements": a list of {"text": short label,
    "x_pct": 0-100, "y_pct": 0-100, "reveal_at": 0.0-1.0} positioned
    sensibly (stacked vertically or arranged left-to-right), with
    "reveal_at" staggered (0.0, 0.33, 0.66 for 3) so they appear in
    sequence. Optionally "connections": [index,index] pairs to draw a
    glowing line between related nodes. Include "title" and
    "accent_color" (hex).

  - "counter": the moment is about ONE specific stat/number. Provide
    "counter_value" (e.g. "92%", "30", "$10K") and "counter_label" (a
    few words, e.g. "days" or "of creators skip this"), plus "title"
    and "accent_color".

  - "dynamic": everything else — one idea/statement that isn't a list
    or a single stat. Provide "title" (max 6 words, punchy, never
    verbatim transcript), 0-3 "bullets" (max 5 words each, optional —
    omit if the title alone carries it), and "accent_color". This scene
    type always renders as a living, moving graphic (animated gradient
    background + drifting glowing shapes) — never flat or static, so
    don't worry about describing motion yourself, just give strong
    content.

Decide, using your own judgment based on the script, whether consecutive
segments should read as ONE continuous evolving graphic (reuse the same
accent_color/layout_type) or as DISTINCT scenes per moment — whichever
fits the content and pacing better.

Return EXACTLY this JSON shape, nothing else, including only the fields
relevant to each segment's chosen layout_type:
{
  "scenes": [
    {"segment_id": "seg_0", "layout_type": "dynamic", "title": "...",
     "bullets": ["...", "..."], "accent_color": "#4EA8FF"},
    {"segment_id": "seg_5", "layout_type": "diagram", "title": "...",
     "accent_color": "#4EA8FF",
     "elements": [
       {"text": "Lead entry", "x_pct": 60, "y_pct": 25, "reveal_at": 0.0},
       {"text": "Contract creation", "x_pct": 60, "y_pct": 50, "reveal_at": 0.33},
       {"text": "Follow-ups", "x_pct": 60, "y_pct": 75, "reveal_at": 0.66}
     ],
     "connections": [[0,1],[1,2]]},
    {"segment_id": "seg_9", "layout_type": "counter", "title": "...",
     "counter_value": "30", "counter_label": "days", "accent_color": "#4EA8FF"}
  ]
}
Every segment id from the input must appear exactly once.
"""


def _default_scene(segment: Segment) -> SceneEvent:
    """Fallback if the AI call fails entirely — still uses the animated
    "dynamic" template rather than a flat static one."""
    title = segment.text.strip()
    if len(title) > 40:
        title = title[:37].rstrip() + "..."
    return SceneEvent(
        segment_id=segment.id, start=segment.start, end=segment.end,
        layout_type="dynamic", title=title or "...", bullets=[],
        accent_color="#4EA8FF",
    )


def run_scene_designer(segments: list[Segment], treatment: str | None = None) -> list[SceneEvent]:
    settings = get_settings()
    fallback = [_default_scene(s) for s in segments]

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        segments_json = json.dumps(
            [{"id": s.id, "start": s.start, "end": s.end, "text": s.text} for s in segments],
            indent=2,
        )
        user_content = f"Segments:\n{segments_json}"
        if treatment:
            user_content = f"Creative Director's treatment:\n{treatment}\n\n{user_content}"

        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        by_id = {s["segment_id"]: s for s in data.get("scenes", []) if s.get("segment_id")}

        scenes: list[SceneEvent] = []
        for segment in segments:
            raw = by_id.get(segment.id)
            if not raw:
                scenes.append(_default_scene(segment))
                continue

            layout_type = raw.get("layout_type") if raw.get("layout_type") in VALID_LAYOUT_TYPES else "dynamic"

            elements = []
            for el in raw.get("elements", [])[:5]:
                try:
                    elements.append(
                        SceneElement(
                            text=str(el.get("text", ""))[:30],
                            x_pct=max(0.0, min(100.0, float(el.get("x_pct", 50.0)))),
                            y_pct=max(0.0, min(100.0, float(el.get("y_pct", 50.0)))),
                            reveal_at=max(0.0, min(1.0, float(el.get("reveal_at", 0.0)))),
                        )
                    )
                except (TypeError, ValueError):
                    continue

            connections = []
            for pair in raw.get("connections", []):
                if isinstance(pair, list) and len(pair) == 2:
                    try:
                        a, b = int(pair[0]), int(pair[1])
                        if 0 <= a < len(elements) and 0 <= b < len(elements):
                            connections.append([a, b])
                    except (TypeError, ValueError):
                        continue

            if layout_type == "diagram" and not elements:
                layout_type = "dynamic"  # no usable elements — fall back to the animated dynamic template

            scenes.append(
                SceneEvent(
                    segment_id=segment.id,
                    start=segment.start,
                    end=segment.end,
                    layout_type=layout_type,
                    title=(raw.get("title") or segment.text)[:60],
                    bullets=[b[:40] for b in raw.get("bullets", [])[:3]],
                    shape="circle",
                    accent_color=raw.get("accent_color") or "#4EA8FF",
                    elements=elements,
                    connections=connections,
                    counter_value=str(raw.get("counter_value", ""))[:12],
                    counter_label=str(raw.get("counter_label", ""))[:30],
                )
            )
        logger.info(
            "Scene Designer: produced %d scenes (%d diagram, %d counter, %d dynamic)",
            len(scenes),
            sum(1 for s in scenes if s.layout_type == "diagram"),
            sum(1 for s in scenes if s.layout_type == "counter"),
            sum(1 for s in scenes if s.layout_type == "dynamic"),
        )
        return scenes
    except Exception:
        logger.exception("Scene Designer failed — falling back to plain transcript-based dynamic scenes")
        return fallback
