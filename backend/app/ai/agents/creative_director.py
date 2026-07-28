"""
Agent 0: Creative Director.

Job: think creatively about THIS specific video before any other agent
touches it. Runs first, produces a short, plain-English creative
treatment (not JSON, no fixed fields) that the other agents receive as
extra context — instead of each agent guessing in a vacuum, they're now
executing a specific creative vision for this video.

Two-step process:
  1. Web-search for current short-form video editing trends/techniques
     (hooks, transitions, pacing, PIP/bubble cutaways, etc.) so this
     agent isn't limited to whatever was true at training time.
  2. Write a treatment for this transcript, informed by those trends.

Falls back to a small curated list of enduring, well-known techniques if
the web search step fails for any reason — a video with a generic-but-
sound treatment is better than no treatment at all.
"""
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment

logger = logging.getLogger(__name__)

FALLBACK_TECHNIQUES = """\
- Fast hook in the first 1-2 seconds, no slow intro
- Picture-in-picture "bubble" cutaway: speaker shrinks into a circle in a
  corner while B-roll fills the frame, then pops back to full-frame
- Whip-pan or hard cut transitions between topic changes
- Kinetic word-by-word captions with one emphasized keyword per beat
- Speed ramps on transitional lines (slow to normal, or a quick speed-up)
- Pattern interrupts every 3-5 seconds to re-engage a drifting viewer
"""

SEARCH_QUERY = "trending short-form video editing techniques Reels TikTok Shorts hooks transitions"


def _fetch_current_trends() -> str:
    """Web-searches for current editing trends via OpenAI's hosted web
    search tool. Falls back to a curated, enduring list if the search
    call fails for any reason (API/model/network issue) — never blocks
    the pipeline."""
    settings = get_settings()
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.responses.create(
            model=settings.openai_director_model,
            tools=[{"type": "web_search_preview"}],
            input=(
                f"Search for: {SEARCH_QUERY}. Summarize 5-8 specific, "
                "concrete, currently-popular short-form video editing "
                "techniques (hooks, transitions, caption styles, cutaway "
                "effects, pacing tricks). Be specific and actionable, not "
                "generic. Plain text list, no citations needed."
            ),
        )
        summary = response.output_text.strip()
        if summary:
            logger.info("Creative Director: fetched live trend summary (%d chars)", len(summary))
            return summary
        raise ValueError("Empty trend summary returned")
    except Exception:
        logger.exception(
            "Creative Director: live trend search failed — falling back to curated technique list"
        )
        return FALLBACK_TECHNIQUES


TREATMENT_SYSTEM_PROMPT = """\
You are the Creative Director for a short-form video. You think creatively
about THIS specific video before anyone else touches it — your job is to
have a genuine point of view, not to fill in a form.

You'll be given:
  - A timestamped transcript
  - A style preset
  - A summary of currently popular short-form editing techniques

Write a short creative treatment (150-300 words, plain English prose, NOT
JSON) describing your vision for how this specific video should be cut.
Reference specific timestamps/segments where relevant. Be concrete: name
the actual technique and where it goes (e.g. "at 00:14 when he explains
the server setup, cut to a picture-in-picture bubble — his face shrinks
to a circle in the bottom-right, B-roll of a terminal window fills the
frame, then pop him back to full-frame at 00:22").

You are not constrained to any fixed list — pull from the current trends
you're given, or use your own judgment for what would make this specific
video scroll-stopping. Other specialized editors will translate your
vision into exact technical decisions afterward, so think like a creative
director pitching an edit, not like an engineer filling out a spec.
"""


def run_creative_director(segments: list[Segment], style_preset: str) -> str:
    """Returns a plain-English creative treatment string. Falls back to a
    short generic note (not a crash) if the call fails."""
    settings = get_settings()
    trends = _fetch_current_trends()

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        transcript_lines = "\n".join(
            f"[{s.start:.1f}s-{s.end:.1f}s] {s.text}" for s in segments
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            messages=[
                {"role": "system", "content": TREATMENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Style preset: {style_preset}\n\n"
                        f"Current trending techniques:\n{trends}\n\n"
                        f"Transcript:\n{transcript_lines}"
                    ),
                },
            ],
        )
        treatment = response.choices[0].message.content.strip()
        logger.info("Creative Director: produced treatment (%d chars)", len(treatment))
        return treatment
    except Exception:
        logger.exception("Creative Director failed — proceeding with no treatment")
        return (
            "No specific creative treatment available for this video — "
            "other agents should use their own default judgment."
        )
