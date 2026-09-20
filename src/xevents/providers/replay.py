"""Replay provider: reads normalized events from a scenario fixture directory.

Each ``fixtures/events/<scenario>/`` holds ``events.json`` (a list of Event records built
by that scenario's ``build.py`` from the raw archived sources kept alongside) and a
``README.md`` with provenance. The events are the same model the live providers produce.
"""

from __future__ import annotations

import json
from pathlib import Path

from xevents.models import Event, EventSource, TimeWindow
from xevents.providers.base import FIXTURES_DIR, EventProvider, ProviderError

EVENTS_DIR = FIXTURES_DIR / "events"


def list_scenarios(events_dir: Path = EVENTS_DIR) -> list[str]:
    return sorted(p.parent.name for p in events_dir.glob("*/events.json"))


def load_scenario(scenario: str, events_dir: Path = EVENTS_DIR) -> list[Event]:
    path = events_dir / scenario / "events.json"
    if not path.exists():
        raise ProviderError(f"scenario '{scenario}' has no events.json at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    events = [Event.model_validate(item) for item in raw]
    for e in events:
        if e.scenario != scenario:
            raise ProviderError(f"{path}: event {e.event_key} has scenario={e.scenario!r}")
    return events


class ReplayProvider(EventProvider):
    source = EventSource.REPLAY

    def __init__(self, scenario: str, events_dir: Path = EVENTS_DIR) -> None:
        self.scenario = scenario
        self.events_dir = events_dir

    def fetch(self, window: TimeWindow) -> list[Event]:
        events = load_scenario(self.scenario, self.events_dir)
        return [e for e in events if e.expires >= window.start and e.onset <= window.end]

    def window(self) -> TimeWindow:
        """The scenario's own extent, for callers that want 'everything in the fixture'."""
        events = load_scenario(self.scenario, self.events_dir)
        return TimeWindow(start=min(e.onset for e in events), end=max(e.expires for e in events))
