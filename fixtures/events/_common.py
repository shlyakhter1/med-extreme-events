"""Shared helpers for scenario builders (fixtures/events/<scenario>/build.py)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from xevents.models import Event

IEM_WATCHWARN = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py"
IEM_UGCS = "https://mesonet.agron.iastate.edu/api/1/nws/ugcs.geojson"
UA = {
    "User-Agent": "med-extreme-events fixture builder (https://github.com/shlyakhter1/med-extreme-events)"
}


def download(
    url: str, dest: Path, params: dict[str, str] | None = None, *, refresh: bool = False
) -> Path:
    """GET → file, skipped when the file already exists (raw pulls are kept in git)."""
    if dest.exists() and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300, headers=UA, follow_redirects=True) as c:
        r = c.get(url, params=params)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


def iem_csv(dest: Path, *, start: str, end: str, phenomena: str, significance: str) -> Path:
    return download(
        IEM_WATCHWARN,
        dest,
        {
            "accept": "csv",
            "sts": start,
            "ets": end,
            "phenomena": phenomena,
            "significance": significance,
            "limit1": "no",
        },
    )


def iem_zones(dest: Path, *, state: str, valid: str) -> Path:
    return download(IEM_UGCS, dest, {"state": state, "just_zones": "1", "valid": valid})


def write_events(scenario_dir: Path, events: list[Event]) -> Path:
    out = scenario_dir / "events.json"
    events = sorted(events, key=lambda e: (e.onset, e.event_key))
    out.write_text(
        json.dumps([e.model_dump(mode="json") for e in events], indent=1, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"wrote {out} ({len(events)} events, built {stamp})")
    return out
