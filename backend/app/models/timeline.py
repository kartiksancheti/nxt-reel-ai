"""
Timeline JSON schema.

This is the single contract in the whole system: the AI Director decides
WHAT should happen, the AI Editor decides HOW, the Designer Engine creates
visuals — all of it gets compiled into a Timeline. The Render Engine never
makes creative decisions; it only ever reads this structure and executes it.

If it isn't in the Timeline, the renderer doesn't do it.
"""
from enum import StrEnum

from pydantic import BaseModel, Field


class VisualSource(StrEnum):
    BROWSER = "browser"
    STOCK_FOOTAGE = "stock_footage"
    MOTION_GRAPHICS = "motion_graphics"
    IMAGE_GENERATION = "image_generation"
    UI_TEMPLATE = "ui_template"
    ORIGINAL_FOOTAGE = "original_footage"


class CameraMove(StrEnum):
    NONE = "none"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    SHAKE = "shake"


class CaptionStyle(BaseModel):
    font: str = "Inter-Bold"
    size: int = 64
    color: str = "#FFFFFF"
    highlight_color: str = "#FFE600"
    position: str = "center"  # center | bottom | top
    animation: str = "word_pop"  # word_pop | typewriter | karaoke


class Word(BaseModel):
    text: str
    start: float
    end: float


class Segment(BaseModel):
    """One sentence/beat of the talking-head transcript."""

    id: str
    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)
    is_hook: bool = False
    is_pattern_interrupt: bool = False


class VisualEvent(BaseModel):
    """A single visual decision layered on top of a segment: B-roll, motion
    graphic, browser recording clip, zoom, etc."""

    segment_id: str
    source: VisualSource
    start: float
    end: float
    asset_ref: str | None = None  # path/URL resolved by the relevant engine
    prompt: str | None = None  # for image/motion-graphics generation
    camera_move: CameraMove = CameraMove.NONE
    z_index: int = 0


class AudioEvent(BaseModel):
    kind: str  # "music" | "sfx"
    asset_ref: str
    start: float
    end: float
    volume_db: float = 0.0


class CTAEvent(BaseModel):
    segment_id: str
    text: str
    start: float
    end: float


class Timeline(BaseModel):
    project_id: str
    style_preset: str
    duration: float
    fps: int = 30
    resolution: tuple[int, int] = (1080, 1920)

    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    segments: list[Segment] = Field(default_factory=list)
    visual_events: list[VisualEvent] = Field(default_factory=list)
    audio_events: list[AudioEvent] = Field(default_factory=list)
    cta_events: list[CTAEvent] = Field(default_factory=list)

    class Config:
        use_enum_values = True
