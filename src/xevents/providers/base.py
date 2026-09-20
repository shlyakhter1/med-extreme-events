"""EventProvider contract shared by live feeds and replay."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from xevents.models import Event, EventSource, TimeWindow

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "fixtures"


class ProviderError(RuntimeError):
    pass


class EventProvider(ABC):
    """``fetch(window)`` returns normalized events overlapping ``window``."""

    source: EventSource

    @abstractmethod
    def fetch(self, window: TimeWindow) -> list[Event]: ...
