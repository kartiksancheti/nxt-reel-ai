"""
Instagram Caption Writer.

Generates 3 distinct caption variants for a finished reel, each using a
different structural "shape" (number drop, contrarian hook, story open,
etc.) so the three options don't all read like the same template with
swapped words. This is a SEPARATE concern from the video pipeline — it
runs off the transcript alone, any time after transcription, and never
touches the Timeline/render path.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SHAPES = [
    "stat/number-drop opening",
    "contrarian/pattern-interrupt opening",
    "one-liner thesis + short paragraph",
    "question-hook opening",
    "story/scene opening",
    "direct-address second-person opening",
]

SYSTEM_PROMPT = """\
You write Instagram captions for short-form video reels. For the given
transcript, write 3 DISTINCT caption variants — each must use a
different structural shape (pick 3 different ones from this list):
{shapes}

Rules for every variant:
- 300-500 characters (count letters, spaces, punctuation)
- Never transcribe the video — understand the topic, then write
  something original about it. If a sentence could be copied verbatim
  from the transcript, that's a failure.
- Casual, direct, confident voice. Short sentences, fragments are fine.
- Maximum ONE emoji per caption.
- NEVER use hashtags.
- NEVER use em dashes, corporate jargon ("leverage", "streamline"), or
  AI-sounding words ("delve", "landscape", "crucial", "foster").
- If a CTA keyword is provided, work it in naturally near the end —
  phrased differently in each of the 3 variants, never the same
  sentence structure twice.
- The 3 variants must feel like 3 different people wrote them — vary
  opening style, sentence rhythm, and closing line.

Return EXACTLY this JSON shape, nothing else:
{{
  "variants": [
    {{"shape": "stat/number-drop opening", "text": "...", "char_count": 412}}
  ]
}}
"""


def run_caption_writer(transcript_text: str, cta_keyword: str | None = None) -> list[dict]:
    settings = get_settings()
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        cta_note = (
            f"\nCTA keyword to include: {cta_keyword}"
            if cta_keyword
            else "\nNo specific CTA keyword given — end with a natural engagement prompt instead."
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(shapes="\n".join(f"- {s}" for s in SHAPES)),
                },
                {"role": "user", "content": f"Video transcript:\n{transcript_text}{cta_note}"},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        variants = data.get("variants", [])
        logger.info("Caption Writer: produced %d variants", len(variants))
        return variants
    except Exception:
        logger.exception("Caption Writer failed — returning no variants")
        return []
