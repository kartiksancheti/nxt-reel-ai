"""
Whisper transcription service.

Responsible only for: audio extraction -> word-level transcript.
Does not make any creative decisions — that's the AI Director's job.
"""
import logging
import subprocess
from pathlib import Path

from openai import OpenAI

from app.core.config import get_settings
from app.models.timeline import Segment, Word

logger = logging.getLogger(__name__)


def extract_audio(video_path: str, output_dir: str) -> str:
    """Extract a mono 16kHz WAV track from the source video via ffmpeg."""
    video_dir = Path(video_path).parent  # already scoped to this project's upload folder
    audio_path = str(video_dir / f"{Path(video_path).stem}.wav")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-ac", "1", "-ar", "16000",
        audio_path,
    ]
    logger.info("Extracting audio: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    return audio_path


def transcribe_audio(audio_path: str) -> dict:
    """Call Whisper (via OpenAI API) for a word-level timestamped transcript."""
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    logger.info("Transcribing %s with Whisper", audio_path)
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            prompt="Yeh video mein hum baat karenge business growth ke baare mein, kaise aap apna kaam grow kar sakte hain.",
        )
    return response.model_dump()


def build_segments(whisper_result: dict) -> list[Segment]:
    """Convert raw Whisper output into typed Segment objects with word timings."""
    segments: list[Segment] = []
    for i, seg in enumerate(whisper_result.get("segments", [])):
        words = [
            Word(text=w["word"].strip(), start=w["start"], end=w["end"])
            for w in seg.get("words", [])
        ]
        segments.append(
            Segment(
                id=f"seg_{i}",
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
                words=words,
            )
        )
    return segments
