"""
UI Template Engine.

Renders pre-built HTML/CSS templates (stat cards, quote cards, comparison
tables, testimonial overlays) via a headless browser screenshot/recording.
This is what powers things like "3 reasons why..." on-screen graphics
without needing After Effects.
"""
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.engines.base import BaseVisualEngine
from app.models.timeline import VisualEvent

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "ui_templates"


class UITemplateEngine(BaseVisualEngine):
    name = "ui_template"

    async def resolve(self, event: VisualEvent, project_id: str) -> str:
        settings = get_settings()
        out_dir = Path(settings.assets_dir) / project_id / "ui_templates"
        out_dir.mkdir(parents=True, exist_ok=True)
        clip_path = out_dir / f"{event.segment_id}.png"

        # asset_ref is expected to be a template name, e.g. "stat_card" or "stat_card.html"
        requested = event.asset_ref or "stat_card"
        template_name = requested if requested.endswith(".html") else f"{requested}.html"
        template_path = TEMPLATES_DIR / template_name

        if not template_path.exists():
            logger.warning(
                "UI template '%s' not found, falling back to stat_card.html", template_name
            )
            template_path = TEMPLATES_DIR / "stat_card.html"

        logger.info("Rendering UI template '%s'", template_path.name)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1080, "height": 1920})
            # TODO: inject event.prompt (JSON payload of copy/stats) into the
            # template via query params or a local dev server before loading.
            await page.goto(f"file://{template_path}")
            await page.screenshot(path=str(clip_path))
            await browser.close()

        return str(clip_path)
