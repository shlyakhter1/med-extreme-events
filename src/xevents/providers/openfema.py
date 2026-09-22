"""OpenFEMA disaster declarations by county → context events.

Source: https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries (no auth). One row
per (disaster, designated area); county rows carry ``fipsStateCode`` + ``fipsCountyCode``.
Declarations are post-hoc context (requirements §4), so they map to the event type of
their incident and carry the disaster number in ``metrics``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from xevents.models import (
    CapCertainty,
    CapSeverity,
    CapUrgency,
    Event,
    EventGeography,
    EventSource,
    EventType,
    Temporality,
    TimeWindow,
)
from xevents.providers.base import EventProvider, ProviderError

BASE_URL = "https://www.fema.gov/api/open/v2"
INCIDENT_TYPES: dict[str, EventType] = {
    "Hurricane": EventType.HURRICANE_FLOOD,
    "Tropical Storm": EventType.HURRICANE_FLOOD,
    "Flood": EventType.HURRICANE_FLOOD,
    "Coastal Storm": EventType.HURRICANE_FLOOD,
    "Severe Storm": EventType.HURRICANE_FLOOD,
    "Fire": EventType.WILDFIRE_SMOKE,
}
SELECT = (
    "disasterNumber,state,declarationType,declarationDate,incidentType,declarationTitle,"
    "incidentBeginDate,incidentEndDate,fipsStateCode,fipsCountyCode,designatedArea"
)
PAGE = 5000  # OpenFEMA's maximum $top; pages continue with $skip until a short page


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC) if value else None


def parse_declarations(rows: list[dict[str, Any]], raw_ref: str | None = None) -> list[Event]:
    """Group county rows by disaster number → one event per declaration."""
    groups: dict[int, dict[str, Any]] = {}
    for r in rows:
        event_type = INCIDENT_TYPES.get(str(r.get("incidentType") or ""))
        county = f"{r.get('fipsStateCode', '')}{r.get('fipsCountyCode', '')}"
        if event_type is None or r.get("fipsCountyCode") in (None, "", "000"):
            continue
        g = groups.setdefault(
            int(r["disasterNumber"]),
            {"row": r, "event_type": event_type, "counties": set(), "states": set()},
        )
        g["counties"].add(county)
        g["states"].add(str(r.get("state")))
    events = []
    for number, g in sorted(groups.items()):
        r = g["row"]
        onset = _dt(r.get("incidentBeginDate")) or _dt(r.get("declarationDate"))
        if onset is None:
            continue
        expires = _dt(r.get("incidentEndDate")) or (onset + timedelta(days=30))
        events.append(
            Event(
                source=EventSource.OPENFEMA,
                source_id=str(number),
                event_type=g["event_type"],
                event_name=f"FEMA {r.get('declarationType')} declaration: {r.get('incidentType')}",
                headline=str(r.get("declarationTitle") or ""),
                severity=CapSeverity.SEVERE
                if r.get("declarationType") == "DR"
                else CapSeverity.MODERATE,
                urgency=CapUrgency.PAST,
                certainty=CapCertainty.OBSERVED,
                temporality=Temporality.OBSERVED,  # a declaration means the event occurred
                onset=onset,
                expires=max(expires, onset),
                sent=_dt(r.get("declarationDate")),
                geography=EventGeography(
                    county_fips=sorted(g["counties"]),
                    states=sorted(g["states"]),
                    note="designated counties from OpenFEMA rows",
                ),
                metrics={
                    "fema_disaster_number": number,
                    "declaration_type": str(r.get("declarationType") or ""),
                    "incident_type": str(r.get("incidentType") or ""),
                    "temporality_basis": "fema declaration",
                },
                raw_ref=raw_ref,
            )
        )
    return events


class OpenFEMAProvider(EventProvider):
    source = EventSource.OPENFEMA

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        raw_dir: Path | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.raw_dir = raw_dir
        self._client = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": os.environ.get("NWS_USER_AGENT") or "med-extreme-events"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def fetch(self, window: TimeWindow) -> list[Event]:
        """Declarations overlapping ``window`` (declared within the 60 days before it)."""
        since = (window.start - timedelta(days=60)).strftime("%Y-%m-%dT00:00:00.000z")
        types = " or ".join(f"incidentType eq '{t}'" for t in INCIDENT_TYPES)
        rows: list[dict[str, Any]] = []
        skip = 0
        while True:  # a busy season exceeds one page; truncation used to be silent
            params = {
                "$filter": f"declarationDate ge '{since}' and ({types})",
                "$select": SELECT,
                "$orderby": "disasterNumber,fipsStateCode,fipsCountyCode",
                "$top": str(PAGE),
                "$skip": str(skip),
            }
            r = self._client.get("/DisasterDeclarationsSummaries", params=params)
            if r.status_code != 200:
                raise ProviderError(f"OpenFEMA: HTTP {r.status_code} {r.text[:200]}")
            page = r.json().get("DisasterDeclarationsSummaries", [])
            rows.extend(page)
            if len(page) < PAGE:
                break
            skip += PAGE
        doc = {"DisasterDeclarationsSummaries": rows}
        raw_ref = None
        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out = self.raw_dir / f"openfema_declarations_{stamp}.json"
            out.write_text(json.dumps(doc), encoding="utf-8")
            raw_ref = str(out)
        events = parse_declarations(rows, raw_ref)
        return [e for e in events if e.expires >= window.start and e.onset <= window.end]
