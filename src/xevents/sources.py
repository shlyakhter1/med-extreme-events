"""Data-source registry for the /sources page.

``data/sources.yaml`` describes every source the demo uses (event, shared and medical
layers); sources not yet connected are read from ``data/hazard_sources.yaml``
(``status: backlog``) so the backlog is kept in one place. Nothing here does I/O beyond
reading those two files — live run status and facility counts are joined in by the view.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LiveStatus(_Strict):
    mode: Literal["live", "reference", "display"]
    runs: list[str] = Field(default_factory=list, description="provider names in feed_runs")
    coverage: str
    coverage_level: Literal["full", "partial", "none"]


class Source(_Strict):
    id: str
    name: str
    layer: Literal["event", "shared", "medical"]
    event_source: str | None = Field(
        default=None, description="EventSource value, to list the replays that carry it"
    )
    facility_counts: bool = False
    provides: str
    drives: str
    live: LiveStatus
    replay: str | None = None
    auth: str
    cadence: str
    limits: list[str] = Field(default_factory=list)
    attribution: str | None = None
    code: str | None = None
    anchor: str | None = None


class Registry(_Strict):
    guide: str
    sources: list[Source]


class BacklogSource(BaseModel):
    """A hazard-catalog row with ``status: backlog``; the catalog has free-form extras."""

    model_config = ConfigDict(extra="ignore")
    id: str
    hazards: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    notes: str | None = None
    scope: str | None = None


@lru_cache(maxsize=1)
def load_registry(path: Path = DATA_DIR / "sources.yaml") -> Registry:
    return Registry.model_validate(yaml.safe_load(path.read_text()))


@lru_cache(maxsize=1)
def load_backlog(path: Path = DATA_DIR / "hazard_sources.yaml") -> list[BacklogSource]:
    doc = yaml.safe_load(path.read_text())
    return [
        BacklogSource.model_validate(s)
        for s in doc.get("sources", [])
        if s.get("status") == "backlog"
    ]
