import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProjectStatus(StrEnum):
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    GENERATING_TIMELINE = "generating_timeline"
    TIMELINE_READY = "timeline_ready"
    RENDERING = "rendering"
    RENDERED = "rendered"
    EXPORTED = "exported"
    FAILED = "failed"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    style_preset: Mapped[str] = mapped_column(String, default="minimal")
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.UPLOADED
    )

    source_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    transcript: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timeline_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    caption_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rendered_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    exported_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
