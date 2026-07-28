"""
Caption style presets.

Deliberately NOT an AI agent. Which font/color/animation a given style
preset uses is a design decision your team makes once, not something
that benefits from being re-decided (and re-billed) on every single
project. This is a plain lookup table — fast, free, and consistent.
"""
from app.models.timeline import CaptionStyle

STYLE_CAPTION_MAP: dict[str, CaptionStyle] = {
    "alex_hormozi": CaptionStyle(
        font="Liberation-Sans-Bold", size=76, color="#FFFFFF",
        highlight_color="#FFE600", position="center", animation="word_pop",
    ),
    "ali_abdaal": CaptionStyle(
        font="Liberation-Sans-Bold", size=58, color="#FFFFFF",
        highlight_color="#4EA8FF", position="bottom", animation="karaoke",
    ),
    "indian_ai_creator": CaptionStyle(
        font="Liberation-Sans-Bold", size=64, color="#FFFFFF",
        highlight_color="#FF8A00", position="center", animation="word_pop",
    ),
    "luxury": CaptionStyle(
        font="Liberation-Serif-Bold", size=54, color="#F5F0E6",
        highlight_color="#D4AF37", position="bottom", animation="typewriter",
    ),
    "minimal": CaptionStyle(
        font="Liberation-Sans", size=50, color="#FFFFFF",
        highlight_color="#FFFFFF", position="bottom", animation="karaoke",
    ),
    "podcast": CaptionStyle(
        font="Liberation-Sans-Bold", size=46, color="#FFFFFF",
        highlight_color="#7CFF6B", position="bottom", animation="karaoke",
    ),
}

DEFAULT_CAPTION_STYLE = STYLE_CAPTION_MAP["minimal"]


def get_caption_style(style_preset: str) -> CaptionStyle:
    return STYLE_CAPTION_MAP.get(style_preset, DEFAULT_CAPTION_STYLE)
