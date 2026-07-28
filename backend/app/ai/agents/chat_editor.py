"""
Chat Editor Agent.

Lets a person describe a change in plain English ("make captions bigger",
"remove the b-roll at 0:14", "change the CTA to say X") against an
ALREADY-GENERATED Timeline, and translates that into a bounded, safe
patch — never a full timeline rewrite. The renderer stays "dumb": this
agent never touches pixels, only the same Timeline JSON every other
agent already produces.

Deliberately narrow scope (mirrors the same "closed list" philosophy as
the Visual Director): this agent can only request a few specific kinds
of change. Anything it can't express in this bounded contract is
reported back to the person as unsupported, rather than inventing new
JSON shapes the rest of the system doesn't understand.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Chat Editor for an already-generated short-form video Timeline.
A person will describe, in plain English, a change they want. You can
ONLY make these kinds of changes:

  - "caption_style_updates": any of font, color, highlight_color,
    position (top/center/bottom), animation (word_pop/karaoke/typewriter),
    size (an integer, roughly 40-90)
  - "remove_visual_segment_ids": a list of segment ids whose B-roll/visual
    overlay should be removed entirely (falls back to plain talking-head
    footage for that moment)
  - "cta_text": new text for the call-to-action, if one exists
  - "unsupported_request": true, with a short explanation, if what the
    person asked for isn't one of the above (e.g. "change my voice",
    "add a new scene", "make me taller" — anything outside caption
    style, removing a visual, or CTA text)

You're given the video's segments (id, start, end, text) so you can map
a description like "the b-roll at 0:14" or "when I talk about pricing"
to the correct segment_id(s).

Return EXACTLY this JSON shape, nothing else, with only the fields that
actually apply (omit ones that don't):
{
  "caption_style_updates": {"color": "#FFFFFF"},
  "remove_visual_segment_ids": ["seg_3"],
  "cta_text": "New CTA text",
  "unsupported_request": false,
  "notes": "One short sentence describing what you changed, to show the person."
}
"""


def run_chat_editor(segments: list[Segment], message: str) -> dict:
    """Returns a bounded patch dict (see SYSTEM_PROMPT contract). Falls
    back to an 'unsupported_request' response if the call fails, rather
    than silently doing nothing with no explanation."""
    settings = get_settings()
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        segments_json = json.dumps(
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
                    "content": f"Segments:\n{segments_json}\n\nRequested change:\n{message}",
                },
            ],
        )
        patch = json.loads(response.choices[0].message.content)
        logger.info(
            "Chat Editor: produced patch %s",
            {k: v for k, v in patch.items() if k != "notes"},
        )
        return patch
    except Exception:
        logger.exception("Chat Editor failed to produce a patch")
        return {
            "unsupported_request": True,
            "notes": "Something went wrong processing that request — please try rephrasing it.",
        }
