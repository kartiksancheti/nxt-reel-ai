from datetime import datetime

from pydantic import BaseModel, field_validator


class ProjectOut(BaseModel):
    id: str
    style_preset: str
    status: str
    created_at: datetime
    updated_at: datetime
    caption_overrides: dict | None = None
    rendered_video_path: str | None = None
    exported_video_path: str | None = None
    error_message: str | None = None

    @field_validator("id", "status", mode="before")
    @classmethod
    def stringify(cls, v):
        return str(v)

    class Config:
        from_attributes = True


class ProjectStatusOut(BaseModel):
    id: str
    status: str
    error_message: str | None = None

    @field_validator("id", "status", mode="before")
    @classmethod
    def stringify(cls, v):
        return str(v)


STYLE_PRESETS = [
    "alex_hormozi",
    "ali_abdaal",
    "indian_ai_creator",
    "luxury",
    "minimal",
    "podcast",
]
