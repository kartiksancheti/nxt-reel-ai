"""
Image Generation Engine.

For visuals that neither stock footage nor motion graphics can cover
(a concept illustration, a stylized thumbnail-style frame), generates a
still image from the AI Director's prompt, which the renderer can then
animate with a zoom/pan (Ken Burns effect).
"""
import base64
import logging
from pathlib import Path

from openai import OpenAI

from app.core.config import get_settings
from app.engines.base import BaseVisualEngine
from app.models.timeline import VisualEvent

logger = logging.getLogger(__name__)


class ImageGenerationEngine(BaseVisualEngine):
    name = "image_generation"

    async def resolve(self, event: VisualEvent, project_id: str) -> str:
        settings = get_settings()
        out_dir = Path(settings.assets_dir) / project_id / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        image_path = out_dir / f"{event.segment_id}.png"

        prompt = event.prompt or "abstract background, cinematic lighting"
        logger.info("Generating image for prompt='%s'", prompt)

        client = OpenAI(api_key=settings.openai_api_key)
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1536",
        )
        image_bytes = base64.b64decode(result.data[0].b64_json)
        image_path.write_bytes(image_bytes)

        return str(image_path)
