"""
Motion Graphics Engine.

Generates a transparent PNG graphic (lower-thirds, animated arrows,
highlight boxes, badges) that the Render Engine composites on top of the
base footage at the right timestamp. Rendered as a still transparent
image rather than a transparent video, since MoviePy/FFmpeg's alpha-video
codecs (qtrle) are unreliable to round-trip; a PNG with alpha is simple,
fast, and always readable back in.
"""
import logging
from pathlib import Path

from moviepy.editor import CompositeVideoClip, TextClip

from app.core.config import get_settings
from app.engines.base import BaseVisualEngine
from app.models.timeline import VisualEvent

logger = logging.getLogger(__name__)


class MotionGraphicsEngine(BaseVisualEngine):
    name = "motion_graphics"

    async def resolve(self, event: VisualEvent, project_id: str) -> str:
        settings = get_settings()
        out_dir = Path(settings.assets_dir) / project_id / "motion_graphics"
        out_dir.mkdir(parents=True, exist_ok=True)
        image_path = out_dir / f"{event.segment_id}.png"

        text = event.prompt or ""
        logger.info("Generating motion graphic (as transparent PNG): '%s'", text)

        txt_clip = TextClip(
            text,
            fontsize=70,
            color="white",
            font="Liberation-Sans-Bold",
            method="caption",
            size=(900, None),
            align="center",
        )
        composite = CompositeVideoClip([txt_clip], size=(1080, 1920))
        composite.save_frame(str(image_path), t=0, withmask=True)

        return str(image_path)
