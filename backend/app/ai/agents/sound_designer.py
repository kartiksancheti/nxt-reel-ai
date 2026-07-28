"""
Agent 5: Sound Designer.

Job: decide background music mood and SFX moments. Critically, this
agent must describe sounds in plain, generic, searchable terms (e.g.
"upbeat corporate", "whoosh", "cash register") rather than inventing
branded-sounding names like "sfx_cash_register_01" — those generic terms
are what actually let the real Freesound/Jamendo search succeed instead
of silently failing to find a match.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import AudioEvent, Segment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Sound Designer for a short-form video. Decide:
  - ONE background music mood/genre for the whole video (plain English,
    e.g. "upbeat corporate", "chill lofi", "energetic hip hop")
  - A handful of specific SFX moments tied to segments, using GENERIC,
    real, searchable sound names only (e.g. "whoosh", "pop", "cash
    register", "ui click", "riser", "impact thud") — never an invented
    specific name.

Background music must always sit well BELOW the speaker's voice —
around -20 to -24 dB is typical for music that supports without
competing. SFX can be a bit louder (-6 to -10 dB) since they're brief.

Return EXACTLY this JSON shape, nothing else:
{
  "music": {"mood": "upbeat corporate", "volume_db": -22},
  "sfx": [
    {"segment_id": "seg_0", "sound": "whoosh", "at": "start", "volume_db": -8}
  ]
}
"at" must be "start" or "end" of the given segment.
"""


def run_sound_designer(segments: list[Segment], total_duration: float) -> list[AudioEvent]:
    """Returns a list of AudioEvent (one music track spanning the whole
    video, plus a handful of SFX events). Falls back to an empty list
    (silent video) if the call fails — the Audio Engine already treats
    missing tracks as skippable, so this keeps that same graceful
    degradation."""
    settings = get_settings()

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        segments_json = json.dumps(
            [{"id": s.id, "start": s.start, "end": s.end, "is_hook": s.is_hook,
              "is_pattern_interrupt": s.is_pattern_interrupt} for s in segments],
            indent=2,
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Segments:\n{segments_json}"},
            ],
        )
        data = json.loads(response.choices[0].message.content)

        events: list[AudioEvent] = []

        music = data.get("music")
        if music and music.get("mood"):
            events.append(
                AudioEvent(
                    kind="music",
                    asset_ref=music["mood"],
                    start=0.0,
                    end=total_duration,
                    volume_db=float(music.get("volume_db", -22)),
                )
            )

        valid_ids = {s.id for s in segments}
        for sfx in data.get("sfx", []):
            seg_id = sfx.get("segment_id")
            if seg_id not in valid_ids or not sfx.get("sound"):
                continue
            segment = next(s for s in segments if s.id == seg_id)
            at_end = sfx.get("at") == "end"
            point = segment.end if at_end else segment.start
            events.append(
                AudioEvent(
                    kind="sfx",
                    asset_ref=sfx["sound"],
                    start=point,
                    end=point + 0.6,
                    volume_db=float(sfx.get("volume_db", -8)),
                )
            )

        logger.info("Sound Designer: %d audio events (music=%s)", len(events), bool(music))
        return events

    except Exception:
        logger.exception("Sound Designer failed — proceeding with a silent video")
        return []
