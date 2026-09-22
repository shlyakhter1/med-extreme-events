"""Scenario guide for the Scenarios page (/replays): the narrative and guided moments in
``data/scenarios.yaml``. Counts, windows and cards fired are computed by the view."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Moment(_Strict):
    at: datetime
    card: str
    caption: str


class Replay(_Strict):
    id: str
    title: str
    region: str
    dates: str
    story: str
    exercises: list[str] = Field(default_factory=list)
    moments: list[Moment] = Field(default_factory=list)


class Cataloged(_Strict):
    title: str
    dates: str
    region: str
    note: str


class LiveGuide(_Strict):
    """The live scenario: not a fixed replay but whatever the feeds say now."""

    title: str
    story: str
    notes: list[str] = Field(default_factory=list)


class Guide(_Strict):
    live: LiveGuide
    replays: list[Replay]
    cataloged: list[Cataloged] = Field(default_factory=list)


@lru_cache(maxsize=1)
def load_guide(path: Path = DATA_DIR / "scenarios.yaml") -> Guide:
    return Guide.model_validate(yaml.safe_load(path.read_text()))
