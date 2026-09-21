"""NOAA HMS smoke polygons → wildfire-smoke events keyed by county.

Source: https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/YYYY/MM/
``hms_smokeYYYYMMDD.zip`` (daily; finalized next morning). Fields: Satellite, Start, End
(``YYYYDDD HHMM`` UTC), Density (Light/Medium/Heavy). Polygon → county coverage uses the
approximate intersection in ``geography.polygons`` (logged simplification; no PostGIS).
"""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import shapefile

from xevents.geography.counties import CountyIndex
from xevents.geography.polygons import counties_covered
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

shapefile.VERBOSE = False  # HMS polygons are often CCW-only; pyshp warns per shape otherwise
BASE_URL = "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile"
DENSITY_SEVERITY = {
    "Light": CapSeverity.MINOR,
    "Medium": CapSeverity.MODERATE,
    "Heavy": CapSeverity.SEVERE,
}


def _parse_hms_time(value: str) -> datetime:
    """``2023158 1310`` → 2023-06-07T13:10Z (day-of-year format)."""
    ydoy, hhmm = value.strip().split()
    base = datetime.strptime(ydoy, "%Y%j").replace(tzinfo=UTC)
    return base + timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[2:]))


def iter_smoke_records(zip_bytes: bytes) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield (attributes, GeoJSON geometry) for each polygon in an HMS shapefile zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        stem = next(n[:-4] for n in zf.namelist() if n.endswith(".shp"))
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(stem + ".shp")),
            dbf=io.BytesIO(zf.read(stem + ".dbf")),
            shx=io.BytesIO(zf.read(stem + ".shx")),
        )
        for sr in reader.iterShapeRecords():
            yield sr.record.as_dict(), dict(sr.shape.__geo_interface__)


def parse_smoke(
    zip_bytes: bytes, day: date, counties: CountyIndex, raw_ref: str | None = None
) -> list[Event]:
    """One daily HMS file → one event per (day, density) covering the union of its polygons.

    Individual polygons are many and overlapping; the card trigger is county-level smoke
    presence by density, so aggregating per density keeps the event store readable while
    preserving polygon provenance in ``geography.polygon`` (MultiPolygon).
    """
    by_density: dict[str, dict[str, Any]] = {}
    for attrs, geom in iter_smoke_records(zip_bytes):
        density = str(attrs.get("Density") or "Unknown")
        bucket = by_density.setdefault(
            density, {"counties": set(), "polys": [], "start": None, "end": None}
        )
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        bucket["polys"].extend(polys)
        bucket["counties"].update(counties_covered(geom, counties))
        try:
            start, end = _parse_hms_time(str(attrs["Start"])), _parse_hms_time(str(attrs["End"]))
        except (ValueError, KeyError):
            continue
        bucket["start"] = start if bucket["start"] is None else min(bucket["start"], start)
        bucket["end"] = end if bucket["end"] is None else max(bucket["end"], end)
    events = []
    day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    for density, b in sorted(by_density.items()):
        if not b["counties"]:
            continue
        onset = b["start"] or day_start
        expires = b["end"] or (day_start + timedelta(days=1))
        events.append(
            Event(
                source=EventSource.HMS,
                source_id=f"{day.isoformat()}:{density.lower()}",
                event_type=EventType.WILDFIRE_SMOKE,
                event_name=f"HMS smoke ({density})",
                headline=f"NOAA HMS {density.lower()} smoke, {day.isoformat()}",
                severity=DENSITY_SEVERITY.get(density, CapSeverity.UNKNOWN),
                urgency=CapUrgency.EXPECTED,
                certainty=CapCertainty.OBSERVED,
                temporality=Temporality.OBSERVED,  # HMS is a satellite analysis product
                onset=onset,
                expires=max(expires, onset),
                geography=EventGeography(
                    county_fips=sorted(b["counties"]),
                    polygon={"type": "MultiPolygon", "coordinates": b["polys"]},
                    note=(
                        "counties by approximate polygon intersection "
                        "(representative point / vertex test)"
                    ),
                ),
                metrics={
                    "smoke_density": density,
                    "polygon_count": len(b["polys"]),
                    "temporality_basis": "hms smoke analysis",
                },
                raw_ref=raw_ref,
            )
        )
    return events


class HMSSmokeProvider(EventProvider):
    source = EventSource.HMS

    def __init__(
        self,
        counties: CountyIndex,
        *,
        base_url: str = BASE_URL,
        raw_dir: Path | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.counties = counties
        self.raw_dir = raw_dir
        self._client = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": os.environ.get("NWS_USER_AGENT") or "med-extreme-events"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_day(self, day: date) -> list[Event]:
        path = f"/{day:%Y}/{day:%m}/hms_smoke{day:%Y%m%d}.zip"
        r = self._client.get(path)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise ProviderError(f"GET {path}: HTTP {r.status_code}")
        raw_ref = None
        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            out = self.raw_dir / f"hms_smoke{day:%Y%m%d}.zip"
            out.write_bytes(r.content)
            raw_ref = str(out)
        return parse_smoke(r.content, day, self.counties, raw_ref)

    def fetch(self, window: TimeWindow) -> list[Event]:
        """Daily files for each day in the window (today's file may not exist yet → skipped)."""
        events: list[Event] = []
        day = window.start.date()
        while day <= window.end.date():
            events.extend(self.fetch_day(day))
            day += timedelta(days=1)
        return events
