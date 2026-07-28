"""
Celery application for long-running, async work: transcription, AI Director
timeline generation, and rendering. These jobs can take minutes, so they
run in the `worker` container instead of blocking API requests.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nxt_reel_ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.services.render_service",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
