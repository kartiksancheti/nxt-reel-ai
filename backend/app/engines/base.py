"""
Every visual engine implements the same contract: given a VisualEvent
(a decision already made by the AI Director), resolve it into an actual
asset on disk (image, video clip, or animation) that the Render Engine
can drop into the timeline.

Engines never make creative decisions — they only fulfill decisions
already made. This keeps "AI decides everything; renderer only executes"
true at every layer, not just the top one.
"""
from abc import ABC, abstractmethod

from app.models.timeline import VisualEvent


class BaseVisualEngine(ABC):
    name: str

    @abstractmethod
    async def resolve(self, event: VisualEvent, project_id: str) -> str:
        """Resolve a VisualEvent into a file path for the asset it produces.

        Must be idempotent-ish: safe to call again if a prior render step
        failed partway through.
        """
        raise NotImplementedError
