"""
Browser Engine.

Uses Playwright to record real browser interactions (e.g. showing a
product UI, a website, a search result) as a video clip, per a
VisualEvent's `prompt`/`asset_ref` (a URL and a set of actions decided
by the AI Director/Editor).
"""
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.engines.base import BaseVisualEngine
from app.models.timeline import VisualEvent

logger = logging.getLogger(__name__)


class BrowserEngine(BaseVisualEngine):
    name = "browser"

    async def resolve(self, event: VisualEvent, project_id: str) -> str:
        settings = get_settings()
        out_dir = Path(settings.assets_dir) / project_id / "browser"
        out_dir.mkdir(parents=True, exist_ok=True)
        clip_path = out_dir / f"{event.segment_id}.webm"

        url = event.asset_ref
        if not url:
            raise ValueError(f"Browser engine event {event.segment_id} has no target URL")

        logger.info("Recording browser session for %s -> %s", url, clip_path)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                record_video_dir=str(out_dir),
                viewport={"width": 1080, "height": 1920},
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle")
            # TODO: replay AI-Director-specified actions (scroll, click, type)
            await page.wait_for_timeout(int((event.end - event.start) * 1000))
            await context.close()
            await browser.close()

        return str(clip_path)
