"""
YouTube Description Writer.

Generates a locked-structure YouTube description (title, summary,
benefit bullets, optional CTA, optional social links,
hashtags) for a finished video. The STRUCTURE/rules are fixed; WHICH
products/socials appear is entirely configurable via Settings — nothing
here is hardcoded to any specific creator's brand. Any block whose
setting isn't configured is simply omitted rather than showing a
placeholder.
"""
import json
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You write a YouTube/social video description for a short-form
talking-head video (Reels, Shorts, TikTok-length content). Given the
transcript, produce:
  - a title (if not already given)
  - a 2-4 sentence plain-English summary naming what the video covers
  - 4 benefit bullets (5-10 words each)
  - 3 lowercase hashtags relevant to the topic

Never use em dashes. No emoji in the body.

Return EXACTLY this JSON shape, nothing else:
{
  "title": "...",
  "summary": "...",
  "benefits": ["...", "...", "...", "..."],
  "hashtags": ["tag1", "tag2", "tag3"]
}
"""


def _format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def run_description_writer(segments: list[Segment], cta_keyword: str | None = None) -> dict:
    settings = get_settings()

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        transcript_json = json.dumps(
            [{"start": _format_timestamp(s.start), "text": s.text} for s in segments],
            indent=2,
        )
        response = client.chat.completions.create(
            model=settings.openai_director_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Transcript:\n{transcript_json}"},
            ],
        )
        data = json.loads(response.choices[0].message.content)
    except Exception:
        logger.exception("Description Writer failed — returning minimal stub")
        data = {
            "title": "Video",
            "summary": "",
            "benefits": [],
            "hashtags": [],
        }

    lines: list[str] = []
    if settings.creator_community_url:
        label = settings.creator_community_label or "Community"
        lines.append(f"Learn more ({label}): {settings.creator_community_url}")
        lines.append("")

    lines.append(data.get("title", ""))
    lines.append("")
    lines.append(data.get("summary", ""))
    lines.append("")

    benefits = data.get("benefits", [])
    if benefits:
        lines.append("In this video you'll learn:")
        for b in benefits:
            lines.append(f"\u2022 {b}")
        lines.append("")

    if cta_keyword:
        lines.append(f'Comment "{cta_keyword}" and let me know what you think.')
        lines.append("")

    socials = []
    if settings.creator_instagram_url:
        socials.append(f"* Instagram: {settings.creator_instagram_url}")
    if settings.creator_youtube_url:
        socials.append(f"* YouTube: {settings.creator_youtube_url}")
    if settings.creator_tiktok_url:
        socials.append(f"* TikTok: {settings.creator_tiktok_url}")
    if settings.creator_linkedin_url:
        socials.append(f"* LinkedIn: {settings.creator_linkedin_url}")
    if settings.creator_community_url:
        label = settings.creator_community_label or "Community"
        socials.append(f"* {label}: {settings.creator_community_url}")
    if socials:
        lines.append("CONNECT WITH ME")
        lines.extend(socials)
        lines.append("")

    hashtags = data.get("hashtags", [])
    if hashtags:
        lines.append(" ".join(f"#{h}" for h in hashtags))

    data["full_description"] = "\n".join(lines).strip()
    return data
