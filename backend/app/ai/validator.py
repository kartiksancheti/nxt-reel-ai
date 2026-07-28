"""
Timeline Validator.

The AI Director sometimes invents things that don't actually exist:
a UI template filename that was never built, a "URL" that's really just
a scene description, an audio track name pulled from nowhere. Rather
than discover this at render time (expensive, slow, and this exact
pattern caused nearly every bug we hit in production), this module runs
right after the Director generates a Timeline and deterministically
checks/fixes every reference against what's actually real.

Nothing here makes creative decisions — it only ever downgrades an
invalid reference to a safe, working fallback, or drops something that
can't be salvaged. Every fix is logged so it's visible what got changed
and why.
"""
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from app.models.timeline import Timeline, VisualSource

logger = logging.getLogger(__name__)

UI_TEMPLATES_DIR = Path(__file__).parent.parent / "engines" / "ui_templates"
FALLBACK_UI_TEMPLATE = "stat_card.html"
MAX_MOTION_GRAPHICS_DURATION = 5.0


def _real_ui_template_names() -> set[str]:
    if not UI_TEMPLATES_DIR.exists():
        return set()
    return {p.name for p in UI_TEMPLATES_DIR.glob("*.html")}


def get_real_ui_template_names() -> set[str]:
    """Public accessor — used by the Visual Director agent to know what
    templates actually exist before it ever generates a Timeline."""
    return _real_ui_template_names()


def _is_real_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _slugify_asset_ref(value: str) -> str:
    """Normalize an audio asset name into a clean, filesystem/search-safe
    slug (lowercase, single underscores, no punctuation)."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_") or "sound"


def validate_and_fix_timeline(timeline: Timeline) -> Timeline:
    """Mutates and returns the given Timeline with every invalid
    reference fixed or dropped. Safe to call on any Timeline, including
    ones with no issues at all (no-op in that case)."""
    valid_segment_ids = {s.id for s in timeline.segments}
    real_templates = _real_ui_template_names()

    fixed_visual_events = []
    for event in timeline.visual_events:
        if event.segment_id not in valid_segment_ids:
            logger.warning(
                "Dropping visual_event referencing unknown segment_id=%s", event.segment_id
            )
            continue

        if event.source == VisualSource.UI_TEMPLATE:
            template_name = event.asset_ref or ""
            if not template_name.endswith(".html"):
                template_name = f"{template_name}.html"
            if template_name not in real_templates:
                logger.warning(
                    "UI template '%s' doesn't exist — falling back to '%s' (segment=%s)",
                    event.asset_ref, FALLBACK_UI_TEMPLATE, event.segment_id,
                )
                event.asset_ref = FALLBACK_UI_TEMPLATE

        elif event.source == VisualSource.BROWSER:
            if not _is_real_url(event.asset_ref):
                logger.warning(
                    "Browser event has no real URL ('%s') — downgrading to stock_footage (segment=%s)",
                    event.asset_ref, event.segment_id,
                )
                event.source = VisualSource.STOCK_FOOTAGE
                if not event.prompt:
                    event.prompt = event.asset_ref or "relevant b-roll footage"
                event.asset_ref = None

        if event.source == VisualSource.MOTION_GRAPHICS:
            max_end = event.start + MAX_MOTION_GRAPHICS_DURATION
            if event.end > max_end:
                logger.warning(
                    "Motion graphic on segment=%s runs %.1fs — clamping to %.1fs",
                    event.segment_id, event.end - event.start, MAX_MOTION_GRAPHICS_DURATION,
                )
                event.end = max_end

        fixed_visual_events.append(event)
    timeline.visual_events = fixed_visual_events

    fixed_audio_events = []
    for event in timeline.audio_events:
        original_ref = event.asset_ref
        event.asset_ref = _slugify_asset_ref(original_ref)
        if event.asset_ref != original_ref:
            logger.info("Normalized audio asset_ref '%s' -> '%s'", original_ref, event.asset_ref)

        # Hard safety ceiling: whatever the Sound Designer picked, music
        # must never be loud enough to compete with the speaker's voice.
        # This is enforced here regardless of the agent's own judgment,
        # since a too-loud music bed makes a video unwatchable.
        max_volume_db = -28.0 if event.kind == "music" else -12.0
        if event.volume_db > max_volume_db:
            logger.warning(
                "Clamping %s volume from %.1fdB to %.1fdB (segment/asset=%s)",
                event.kind, event.volume_db, max_volume_db, event.asset_ref,
            )
            event.volume_db = max_volume_db

        fixed_audio_events.append(event)
    timeline.audio_events = fixed_audio_events

    fixed_cta_events = []
    for cta in timeline.cta_events:
        if cta.segment_id not in valid_segment_ids:
            logger.warning("Dropping cta_event referencing unknown segment_id=%s", cta.segment_id)
            continue
        fixed_cta_events.append(cta)
    timeline.cta_events = fixed_cta_events

    return timeline
