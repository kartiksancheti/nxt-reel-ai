"""
Structured logging configuration.

"Logging everywhere" is a project development rule — every module should
`import logging; logger = logging.getLogger(__name__)` and log key
decisions (what the AI Director decided, what the renderer executed, etc).
"""
import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Avoid duplicate handlers on reload
    root.handlers.clear()
    root.addHandler(handler)
