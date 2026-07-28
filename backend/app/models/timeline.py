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
    PIP_OVERLAY = "pip_overlay"


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
    position: str = "center"  # center | bottom | top | safe_top | split_line
    animation: str = "word_pop"  # word_pop | typewriter | karaoke | progressive_reveal


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


class SceneElement(BaseModel):
    """One labeled node in a diagram-style Konva scene — e.g. one step in
    a "lead entry -> contract creation -> follow-ups" sequence. Position
    is given as a percentage (0-100) of the top-half frame, so the Konva
    template can place it regardless of exact pixel resolution.
    reveal_at is a 0.0-1.0 fraction of the scene's own duration — when
    this element animates in relative to the scene's start."""

    text: str
    x_pct: float = 50.0
    y_pct: float = 50.0
    reveal_at: float = 0.0


class SceneEvent(BaseModel):
    """A single Konva.js-rendered scene for the TOP HALF of a 'split_demo'
    layout video (the bottom half is the speaker's talking-head footage).
    Deliberately a closed, structured schema — never free-form code, so
    the Konva engine can render every scene deterministically without any
    injection risk.

    "layout_type" picks which Konva template this scene uses:
      - "simple": a title + up to 3 bullets + one background shape
        (circle/arrow/checklist/flow) — good for a single idea/moment.
      - "diagram": multiple labeled nodes (from "elements"), optionally
        connected by lines (from "connections", pairs of element
        indices) — good for enumerated steps/options mentioned in the
        script (e.g. "lead entry, contract creation, follow-ups").
      - "counter": a single big number/stat that counts up on screen —
        good for a stat callout moment.
    """

    segment_id: str
    start: float
    end: float
    layout_type: str = "simple"  # simple | diagram | counter
    title: str = ""
    bullets: list[str] = Field(default_factory=list)
    shape: str = "circle"  # circle | arrow | checklist | flow (used by "simple" only)
    accent_color: str = "#4EA8FF"
    elements: list[SceneElement] = Field(default_factory=list)  # used by "diagram"
    connections: list[list[int]] = Field(default_factory=list)  # used by "diagram"
    counter_value: str = ""  # used by "counter", e.g. "92%" or "30"
    counter_label: str = ""  # used by "counter", e.g. "days"


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

    layout: str = "full"  # "full" | "split_demo"

    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    segments: list[Segment] = Field(default_factory=list)
    visual_events: list[VisualEvent] = Field(default_factory=list)
    scene_events: list[SceneEvent] = Field(default_factory=list)
    audio_events: list[AudioEvent] = Field(default_factory=list)
    cta_events: list[CTAEvent] = Field(default_factory=list)

    class Config:
        use_enum_values = True
