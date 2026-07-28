"""
Audio Engine (Music + SFX).

Resolves an AudioEvent's `asset_ref` (an invented-sounding name like
"upbeat_track_1" or "stamp_thud") into a real downloaded audio file by
searching real libraries:
  - kind="music" -> Jamendo (Creative Commons music)
  - kind="sfx"   -> Freesound (crowd-sourced sound effects)

Downloads are cached at ASSETS_DIR/music/{asset_ref}.mp3 — the exact
path the Render Engine's _build_audio_track already looks for, so no
changes are needed on the compositing side.
"""
import logging
import re
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.models.timeline import AudioEvent

logger = logging.getLogger(__name__)

FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
JAMENDO_SEARCH_URL = "https://api.jamendo.com/v3.0/tracks/"


def _asset_ref_to_query(asset_ref: str) -> str:
    text = re.sub(r"^(sfx|music)_", "", asset_ref)
    text = re.sub(r"_\d+$", "", text)
    return text.replace("_", " ").strip() or asset_ref


async def _resolve_sfx(event: AudioEvent, dest_path: Path) -> bool:
    settings = get_settings()
    if not settings.freesound_api_key:
        logger.warning("FREESOUND_API_KEY not set — cannot resolve SFX '%s'", event.asset_ref)
        return False

    query = _asset_ref_to_query(event.asset_ref)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            FREESOUND_SEARCH_URL,
            params={
                "query": query,
                "token": settings.freesound_api_key,
                "fields": "id,name,previews,duration",
                "filter": "duration:[0.1 TO 8]",
                "page_size": 1,
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            logger.warning("No Freesound results for SFX query='%s' (asset_ref=%s)", query, event.asset_ref)
            return False

        preview_url = results[0].get("previews", {}).get("preview-hq-mp3")
        if not preview_url:
            logger.warning("Freesound result for '%s' had no preview URL", query)
            return False

        audio_resp = await client.get(preview_url)
        audio_resp.raise_for_status()
        dest_path.write_bytes(audio_resp.content)
        logger.info("Resolved SFX '%s' -> %s (query='%s')", event.asset_ref, dest_path, query)
        return True


async def _resolve_music(event: AudioEvent, dest_path: Path) -> bool:
    settings = get_settings()
    if not settings.jamendo_client_id:
        logger.warning("JAMENDO_CLIENT_ID not set — cannot resolve music '%s'", event.asset_ref)
        return False

    query = _asset_ref_to_query(event.asset_ref)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            JAMENDO_SEARCH_URL,
            params={
                "client_id": settings.jamendo_client_id,
                "format": "json",
                "limit": 1,
                "namesearch": query,
                "audioformat": "mp32",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            logger.warning("No Jamendo results for music query='%s' (asset_ref=%s)", query, event.asset_ref)
            return False

        audio_url = results[0].get("audiodownload") or results[0].get("audio")
        if not audio_url:
            logger.warning("Jamendo result for '%s' had no downloadable audio URL", query)
            return False

        audio_resp = await client.get(audio_url)
        audio_resp.raise_for_status()
        dest_path.write_bytes(audio_resp.content)
        logger.info("Resolved music '%s' -> %s (query='%s')", event.asset_ref, dest_path, query)
        return True


async def resolve_audio_assets(timeline) -> None:
    settings = get_settings()
    music_dir = Path(settings.assets_dir) / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    for event in timeline.audio_events:
        dest_path = music_dir / f"{event.asset_ref}.mp3"
        if dest_path.exists():
            continue
        try:
            if event.kind == "sfx":
                await _resolve_sfx(event, dest_path)
            elif event.kind == "music":
                await _resolve_music(event, dest_path)
        except Exception:
            logger.exception(
                "Failed to resolve audio asset '%s' (kind=%s) — will be skipped at composite time",
                event.asset_ref, event.kind,
            )
