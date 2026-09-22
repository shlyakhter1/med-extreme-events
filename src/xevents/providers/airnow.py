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

import csv
import io
import json
import os
from datetime import UTC, date, datetime, timedelta
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


# AirNow public file archive (files.airnowtech.org, no key): ``daily_data_v2.dat`` columns.
DAILY_V2_COLUMNS = [
    "date",
    "aqsid",
    "site",
    "parameter",
    "units",
    "value",
    "averaging_hours",
    "agency",
    "aqi",
    "category",
    "lat",
    "lon",
    "full_aqsid",
]
# archive parameter names → the names the current API uses (and our metrics)
DAILY_V2_PARAMETERS = {"PM2.5-24hr": "PM2.5", "OZONE-8HR": "OZONE"}


def parse_daily_data_v2(text: str, day: date) -> list[dict[str, Any]]:
    """``daily_data_v2.dat`` rows → the observation-row shape ``parse_observations`` reads.

    The daily file gives one AQI per (site, parameter) for the calendar day; the row is
    stamped at 00:00 UTC of that day so the event spans the day. Rows without an AQI
    (-999) and parameters other than PM2.5 (24 h) and ozone (8 h) are dropped.
    """
    rows: list[dict[str, Any]] = []
    when = datetime(day.year, day.month, day.day, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < len(DAILY_V2_COLUMNS):
            continue
        r = dict(zip(DAILY_V2_COLUMNS, parts, strict=False))
        param = DAILY_V2_PARAMETERS.get(r["parameter"])
        if param is None or r["aqi"] in ("", "-999"):
            continue
        rows.append(
            {
                "Latitude": r["lat"],
                "Longitude": r["lon"],
                "UTC": when,
                "Parameter": param,
                "AQI": r["aqi"],
                "Category": r["category"],
                "SiteName": r["site"],
                "AgencyName": r["agency"],
                "FullAQSCode": r["full_aqsid"],
            }
        )
    return rows


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


# --------------------------------------------------------------------------- keyless files

FILES_BASE_URL = "https://files.airnowtech.org/airnow"
# HourlyAQObs columns that carry a per-pollutant AQI → the parameter name the cards and the
# replay fixtures use. PM10 is left out, as in the key-based provider.
HOURLY_AQI_COLUMNS = {"PM25_AQI": "PM2.5", "OZONE_AQI": "OZONE"}
AQI_CATEGORY_NAMES = {
    "Good": 1,
    "Moderate": 2,
    "Unhealthy for Sensitive Groups": 3,
    "Unhealthy": 4,
    "Very Unhealthy": 5,
    "Hazardous": 6,
}
AQI_CATEGORY_FLOOR = {1: 0, 2: 51, 3: 101, 4: 151, 5: 201, 6: 301}
# reportingarea.dat time-zone abbreviations (US and territories) → UTC offset in hours
TZ_OFFSETS = {
    "EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7, "PDT": -7, "PST": -8,
    "AKDT": -8, "AKST": -9, "HST": -10, "ADT": -3, "AST": -4,
}  # fmt: skip


def aqi_category(aqi: int) -> int:
    """EPA AQI category number for an AQI value."""
    for cat, upper in ((1, 50), (2, 100), (3, 150), (4, 200), (5, 300)):
        if aqi <= upper:
            return cat
    return 6


def parse_hourly_aq_obs(text: str) -> list[dict[str, Any]]:
    """``HourlyAQObs_YYYYMMDDHH.dat`` (CSV, one row per monitor, times in UTC) → the
    observation-row shape ``parse_observations`` reads, one row per pollutant AQI."""
    rows: list[dict[str, Any]] = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            when = datetime.strptime(f"{r['ValidDate']} {r['ValidTime']}", "%m/%d/%Y %H:%M")
        except (KeyError, ValueError):
            continue
        stamp = when.replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M")
        for column, param in HOURLY_AQI_COLUMNS.items():
            raw = (r.get(column) or "").strip()
            if not raw:
                continue
            try:
                aqi = int(float(raw))
            except ValueError:
                continue
            rows.append(
                {
                    "Latitude": r.get("Latitude"),
                    "Longitude": r.get("Longitude"),
                    "UTC": stamp,
                    "Parameter": param,
                    "AQI": aqi,
                    "Category": aqi_category(aqi),
                    "SiteName": r.get("SiteName", ""),
                    "AgencyName": r.get("DataSource", ""),
                }
            )
    return rows


def parse_reporting_area_forecasts(
    text: str,
    counties: CountyIndex,
    *,
    today: date,
    aqi_min: int = 101,
    raw_ref: str | None = None,
) -> list[Event]:
    """``reportingarea.dat`` forecast rows (type ``F``) for today onward → forecast
    air-pollution events, one per (valid day, county, pollutant) at or above ``aqi_min``.

    Forecasts often give only a category ("Unhealthy for Sensitive Groups"); the AQI is then
    the category's lower bound and ``metrics.aqi_basis`` says so. The county is the one
    holding the reporting area's centre point — a forecast area can span several counties,
    which ``geography.note`` records.
    """
    best: dict[tuple[date, str, str], dict[str, Any]] = {}
    for line in text.splitlines():
        f = line.split("|")
        if len(f) < 17 or f[5] != "F":
            continue
        try:
            valid = datetime.strptime(f[1], "%m/%d/%y").date()
            lat, lon = float(f[9]), float(f[10])
        except ValueError:
            continue
        if valid < today:
            continue
        cat = AQI_CATEGORY_NAMES.get(f[13].strip())
        if f[12].strip():
            try:
                aqi, basis = int(float(f[12])), "forecast AQI"
            except ValueError:
                continue
        elif cat is not None:
            aqi, basis = AQI_CATEGORY_FLOOR[cat], f"category floor ({f[13].strip()})"
        else:
            continue
        if aqi < aqi_min:
            continue
        county = counties.lookup(lon, lat)
        if county is None:
            continue
        param = f[11].strip()
        key = (valid, county.geoid, param)
        if key in best and best[key]["aqi"] >= aqi:
            continue
        best[key] = {
            "aqi": aqi,
            "category": cat or aqi_category(aqi),
            "basis": basis,
            "county": county,
            "area": f"{f[7]}, {f[8]}",
            "tz": f[3].strip(),
            "action_day": f[14].strip(),
            "source": f[16].strip(),
        }
    events: list[Event] = []
    for (valid, fips, param), b in sorted(best.items()):
        offset = TZ_OFFSETS.get(b["tz"], 0)
        onset = datetime(valid.year, valid.month, valid.day, tzinfo=UTC) - timedelta(hours=offset)
        label = next(k for k, v in AQI_CATEGORY_NAMES.items() if v == b["category"])
        events.append(
            Event(
                source=EventSource.AIRNOW,
                source_id=f"forecast:{valid.isoformat()}:{fips}:{param.lower()}",
                event_type=EventType.AIR_POLLUTION,
                event_name=f"AQI forecast {label} ({param})",
                headline=f"{b['area']}: {param} forecast {label} for {valid.isoformat()}",
                severity=CATEGORY_SEVERITY.get(b["category"], CapSeverity.UNKNOWN),
                urgency=CapUrgency.FUTURE if valid > onset.date() else CapUrgency.EXPECTED,
                certainty=CapCertainty.LIKELY,
                temporality=AIRNOW_TEMPORALITY["forecast"],
                onset=onset,
                expires=onset + timedelta(hours=24),
                geography=EventGeography(
                    county_fips=[fips],
                    states=[b["county"].state],
                    note=(
                        f"county holding the centre of forecast reporting area {b['area']} "
                        "(the area can span several counties)"
                    ),
                ),
                metrics={
                    "aqi": b["aqi"],
                    "aqi_category": b["category"],
                    "aqi_basis": b["basis"],
                    "parameter": param,
                    "reporting_area": b["area"],
                    "action_day": b["action_day"],
                    "forecast_source": b["source"],
                    "temporality_basis": "airnow reporting-area forecast",
                },
                raw_ref=raw_ref,
            )
        )
    return events


class AirNowFilesProvider(EventProvider):
    """AirNow without a key: the public file feed at files.airnowtech.org.

    Observations: the newest ``HourlyAQObs_YYYYMMDDHH.dat`` (per-monitor AQI, posted a little
    after each hour; the provider walks back up to ``max_hours_back`` hours to find it).
    Forecasts: ``today/reportingarea.dat``. No key and no request quota; raw files are cached
    like every other provider's pulls.
    """

    source = EventSource.AIRNOW

    def __init__(
        self,
        counties: CountyIndex,
        *,
        base_url: str = FILES_BASE_URL,
        raw_dir: Path | None = None,
        max_hours_back: int = 4,
        now: datetime | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.counties = counties
        self.raw_dir = raw_dir
        self.max_hours_back = max_hours_back
        self._now = now
        self.observed_at: datetime | None = None
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"User-Agent": os.environ.get("NWS_USER_AGENT") or "med-extreme-events"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str) -> str | None:
        r = self._client.get(path)
        if r.status_code in (403, 404):
            return None  # not posted yet (S3 answers 403/404 for a missing key)
        if r.status_code != 200:
            raise ProviderError(f"AirNow files {path}: HTTP {r.status_code}")
        return r.text

    def _cache(self, name: str, text: str) -> str | None:
        if self.raw_dir is None:
            return None
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        out = self.raw_dir / name
        out.write_text(text, encoding="utf-8")
        return str(out)

    def latest_hourly(self) -> tuple[str, datetime] | None:
        now = (self._now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
        for back in range(self.max_hours_back + 1):
            hour = now - timedelta(hours=back)
            name = f"HourlyAQObs_{hour:%Y%m%d%H}.dat"
            text = self._get(f"/{hour:%Y}/{hour:%Y%m%d}/{name}")
            if text:
                return text, hour
        return None

    def status_detail(self, events: int) -> str:
        hour = f"{self.observed_at:%Y-%m-%d %H:00}Z" if self.observed_at else "none found"
        return (
            f"hourly monitors {hour} + reporting-area forecasts; {events} county events ≥ AQI 101"
        )

    def fetch(self, window: TimeWindow) -> list[Event]:
        events: list[Event] = []
        hourly = self.latest_hourly()
        if hourly is not None:
            text, hour = hourly
            self.observed_at = hour
            ref = self._cache(f"airnow_HourlyAQObs_{hour:%Y%m%d%H}.dat", text)
            events.extend(parse_observations(parse_hourly_aq_obs(text), self.counties, raw_ref=ref))
        forecast_text = self._get("/today/reportingarea.dat")
        if forecast_text:
            stamp = (self._now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
            ref = self._cache(f"airnow_reportingarea_{stamp}.dat", forecast_text)
            today = (self._now or datetime.now(UTC)).date()
            events.extend(
                parse_reporting_area_forecasts(
                    forecast_text, self.counties, today=today, raw_ref=ref
                )
            )
        if hourly is None and not forecast_text:
            raise ProviderError("AirNow files: neither hourly observations nor forecasts found")
        return [e for e in events if e.expires >= window.start and e.onset <= window.end]
