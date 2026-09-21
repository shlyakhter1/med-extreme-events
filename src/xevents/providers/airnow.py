"""AirNow monitor observations → air-pollution events keyed by county.

Endpoint: ``https://www.airnowapi.org/aq/data/`` ("Observations by Monitoring Site" —
hourly/daily by bounding box), which is in AirNow's retained 2026 service list; the ZIP and
lat/long "current observation" services are the ones retiring in fall 2026, so we avoid
them. Monitors carry lat/lon, so counties come from our own point-in-polygon. Requires
``AIRNOW_API_KEY``; the 500 req/h limit is respected by fetching one bbox per call and
caching raw responses under ``raw_dir``.

Response shape (documented, but **not yet verified with a key** — see PROGRESS.md):
``[{"Latitude", "Longitude", "UTC", "Parameter", "Unit", "AQI", "Category", "SiteName",
"AgencyName", "FullAQSCode", "IntlAQSCode"}, ...]``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from xevents.geography.counties import CountyIndex
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

BASE_URL = "https://www.airnowapi.org"
CONUS_BBOX = "-125.0,24.0,-66.0,50.0"
# Temporality by AirNow product: monitor observations are measured now; the forecast
# endpoint (not wired yet) describes tomorrow's AQI.
AIRNOW_TEMPORALITY: dict[str, Temporality] = {
    "observation": Temporality.OBSERVED,
    "forecast": Temporality.FORECAST,
}
# AQI category thresholds; the card trigger `aqi_min` compares against the county max AQI.
CATEGORY_SEVERITY = {
    1: CapSeverity.MINOR,  # Good
    2: CapSeverity.MINOR,  # Moderate
    3: CapSeverity.MODERATE,  # USG
    4: CapSeverity.SEVERE,  # Unhealthy
    5: CapSeverity.SEVERE,  # Very unhealthy
    6: CapSeverity.EXTREME,  # Hazardous
}


def parse_observations(
    rows: list[dict[str, Any]],
    counties: CountyIndex,
    *,
    aqi_min: int = 101,
    raw_ref: str | None = None,
    product: str = "observation",
) -> list[Event]:
    """Monitor rows → one event per (county, parameter) at or above ``aqi_min`` (USG+).
    ``product`` names the AirNow product the rows came from (``AIRNOW_TEMPORALITY`` key)."""
    temporality = AIRNOW_TEMPORALITY[product]
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        try:
            aqi = int(r["AQI"])
            lat, lon = float(r["Latitude"]), float(r["Longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if aqi < aqi_min:
            continue
        county = counties.lookup(lon, lat)
        if county is None:
            continue
        param = str(r.get("Parameter") or "")
        key = (county.geoid, param)
        when = _parse_utc(str(r.get("UTC") or ""))
        cur = best.get(key)
        if cur is None or aqi > cur["aqi"]:
            best[key] = {
                "aqi": aqi,
                "category": int(r.get("Category") or 0),
                "county": county,
                "site": str(r.get("SiteName") or ""),
                "when": when,
                "param": param,
            }
    events = []
    for (fips, param), b in sorted(best.items()):
        when = b["when"] or datetime.now(UTC)
        events.append(
            Event(
                source=EventSource.AIRNOW,
                source_id=f"{when:%Y-%m-%d}:{fips}:{param.lower()}",
                event_type=EventType.AIR_POLLUTION,
                event_name=f"AQI {b['aqi']} ({param})",
                headline=(
                    f"{b['county'].name}, {b['county'].state}: {param} AQI {b['aqi']} "
                    f"at {b['site']}"
                ),
                severity=CATEGORY_SEVERITY.get(b["category"], CapSeverity.UNKNOWN),
                urgency=CapUrgency.IMMEDIATE,
                certainty=CapCertainty.OBSERVED,
                temporality=temporality,
                onset=when,
                expires=when + timedelta(hours=24),
                geography=EventGeography(
                    county_fips=[fips],
                    states=[b["county"].state],
                    note="county from monitor coordinates (point-in-polygon)",
                ),
                metrics={
                    "aqi": b["aqi"],
                    "aqi_category": b["category"],
                    "parameter": param,
                    "site": b["site"],
                    "temporality_basis": f"airnow {product}",
                },
                raw_ref=raw_ref,
            )
        )
    return events


def _parse_utc(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


class AirNowProvider(EventProvider):
    source = EventSource.AIRNOW

    def __init__(
        self,
        counties: CountyIndex,
        *,
        api_key: str | None = None,
        bbox: str = CONUS_BBOX,
        base_url: str = BASE_URL,
        raw_dir: Path | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        key = api_key or os.environ.get("AIRNOW_API_KEY")
        if not key:
            raise ProviderError("AIRNOW_API_KEY is not set (free at docs.airnowapi.org)")
        self.api_key = key
        self.bbox = bbox
        self.counties = counties
        self.raw_dir = raw_dir
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def fetch(self, window: TimeWindow) -> list[Event]:
        """One request for the whole window (hourly, PM2.5 + ozone, AQI values)."""
        params = {
            "startDate": window.start.astimezone(UTC).strftime("%Y-%m-%dT%H"),
            "endDate": window.end.astimezone(UTC).strftime("%Y-%m-%dT%H"),
            "parameters": "PM25,OZONE",
            "BBOX": self.bbox,
            "dataType": "A",
            "format": "application/json",
            "verbose": "1",
            "monitorType": "2",
            "includerawconcentrations": "0",
            "API_KEY": self.api_key,
        }
        r = self._client.get("/aq/data/", params=params)
        if r.status_code != 200:
            raise ProviderError(f"AirNow /aq/data/: HTTP {r.status_code} {r.text[:200]}")
        rows: list[dict[str, Any]] = r.json()
        raw_ref = None
        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out = self.raw_dir / f"airnow_data_{stamp}.json"
            out.write_text(json.dumps(rows), encoding="utf-8")
            raw_ref = str(out)
        return parse_observations(rows, self.counties, raw_ref=raw_ref)
