import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import content, export, project, render, timeline, transcribe, upload
from app.core.logging import configure_logging
from app.db.models import Base
from app.db.session import engine

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NXT Reel AI",
    description="AI Creative Director for short-form video generation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for now; tighten to your actual domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(transcribe.router)
app.include_router(timeline.router)
app.include_router(render.router)
app.include_router(export.router)
app.include_router(project.router)
app.include_router(content.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("NXT Reel AI backend starting up")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")
