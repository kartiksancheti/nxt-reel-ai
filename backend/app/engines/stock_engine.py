"""
Stock Footage Engine.

Resolves a VisualEvent into a downloaded stock B-roll clip matching the
AI Director's `prompt` (e.g. "city skyline at night", "typing on laptop").
Wire in your preferred provider (Pexels, Storyblocks, Envato, etc.) via
STOCK_FOOTAGE_API_KEY.
"""
import logging
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.engines.base import BaseVisualEngine
from app.models.timeline import VisualEvent

logger = logging.getLogger(__name__)

STOCK_API_BASE = "https://api.pexels.com/videos"  # swap for your provider of choice


class StockFootageEngine(BaseVisualEngine):
    name = "stock_footage"

    async def resolve(self, event: VisualEvent, project_id: str) -> str:
        settings = get_settings()
        out_dir = Path(settings.assets_dir) / project_id / "stock"
        out_dir.mkdir(parents=True, exist_ok=True)
        clip_path = out_dir / f"{event.segment_id}.mp4"

        query = event.prompt or "abstract background"
        logger.info("Searching stock footage for query='%s'", query)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STOCK_API_BASE}/search",
                params={"query": query, "per_page": 1},
                headers={"Authorization": settings.stock_footage_api_key or ""},
            )
            resp.raise_for_status()
            data = resp.json()
            video_url = (
                data.get("videos", [{}])[0]
                .get("video_files", [{}])[0]
                .get("link")
            )
            if not video_url:
                raise RuntimeError(f"No stock footage found for query '{query}'")

            video_bytes = await client.get(video_url)
            clip_path.write_bytes(video_bytes.content)

        return str(clip_path)
