"""EAGLE-I county power outages → observed ``power_outage`` events.

EAGLE-I (Environment for Analysis of Geo-Located Energy Information, ORNL for DOE) collects
utilities' public outage maps into county-level customers-out counts. Two access paths:

- **Live:** an ArcGIS FeatureServer table with the EAGLE-I API fields (``currentOutage``,
  ``currentOutageRunStartTime``, ``countyFIPSCode`` …). FEMA's partner service at
  ``gis.fema.gov`` is the default; it answered *Token Required* on 2026-09-21, so
  ``EAGLEI_TOKEN`` is sent when set and the failure is explained when not. Any mirror with the
  same fields works through ``EAGLEI_FEATURE_URL`` (state emergency-management agencies publish
  public ones). Raw pulls are cached like every other provider.
- **Replay:** the ORNL historical county CSVs (15-minute cadence, 2014–2025;
  ``fips_code,county,state,customers_out,run_start_time``; early years call the count
  ``sum``), sliced by state/county/date and optionally resampled to hourly maxima.

Percent out uses the Moehl et al. modeled county customer counts (published with Brelsford
et al. 2024, Sci Data, doi:10.1038/s41597-024-03095-5) in
``fixtures/reference/eaglei_customers.csv``, not the feed's own coverage fields, so live and
replay share one denominator. Honest-display strings live here so every render uses the
same words: customers are meters, not people; ~8% of US customers are not covered.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from xevents.models import (
    CapCertainty,
    CapSeverity,
    CapUrgency,
    Card,
    Event,
    EventGeography,
    EventSource,
    EventType,
    Temporality,
    TimeWindow,
)
from xevents.providers.base import FIXTURES_DIR, EventProvider, ProviderError

log = logging.getLogger(__name__)

ATTRIBUTION = "Electric customer outage data provided by EAGLE-I, Department of Energy."
CUSTOMERS_CAVEAT = (
    "Customers are electric meters/accounts, not people; a household or a facility is one customer."
)
COVERAGE_CAVEAT = (
    "About 8% of US electric customers (small rural and municipal utilities) are not covered "
    "by EAGLE-I, so counts are a floor."
)
OVERCOUNT_CAVEAT = (
    "customers_out exceeded the modeled county customer count (utility-map double counting "
    "or a denominator vintage mismatch, both documented EAGLE-I data-quality issues); shown "
    "as 100% with the raw value kept in metrics."
)
DENOMINATOR_SOURCE = (
    "Moehl et al. modeled county electric customers (MCC, 2022 vintage; Brelsford et al. 2024, "
    "Sci Data, doi:10.1038/s41597-024-03095-5)"
)
CUSTOMERS_PATH = FIXTURES_DIR / "reference" / "eaglei_customers.csv"

FEMA_FEATURE_URL = (
    "https://gis.fema.gov/arcgis/rest/services/Partner/PowerOutages_EAGLE_I/FeatureServer/0"
)
# EAGLE-I API field names as published on the ArcGIS mirrors (verified 2026-09-21).
FIELDS = {
    "customers_out": "currentOutage",
    "run_start": "currentOutageRunStartTime",
    "fips": "countyFIPSCode",
    "county": "countyName",
    "state": "stateName",
    "covered_customers": "coveredCustomers",
    "model_count": "modelCount",
}
LIVE_POLL_MINUTES = 60
ORNL_POLL_MINUTES = 15
PAGE_SIZE = 2000
# Severity by share of county customers out (thresholds are display buckets, not triggers).
SEVERITY_BY_PCT: list[tuple[float, CapSeverity]] = [
    (50.0, CapSeverity.EXTREME),
    (25.0, CapSeverity.SEVERE),
    (10.0, CapSeverity.MODERATE),
    (0.0, CapSeverity.MINOR),
]
ORNL_COUNT_COLUMNS = ("customers_out", "sum")


@dataclass(frozen=True)
class OutagePoll:
    """One county at one EAGLE-I run: the unit both access paths produce."""

    county_fips: str
    run_start: datetime
    customers_out: int
    county_name: str = ""
    state: str = ""
    extra: dict[str, int] = field(default_factory=dict, hash=False)


# --------------------------------------------------------------------------- denominators


def load_customers(path: Path = CUSTOMERS_PATH) -> dict[str, int]:
    """County FIPS → modeled electric customers (``scripts/build_eaglei_customers.py``)."""
    if not path.exists():
        raise ProviderError(f"{path} missing — run scripts/build_eaglei_customers.py")
    out: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["county_fips"].zfill(5)] = int(r["customers"])
    return out


def min_outage_pct(cards: Iterable[Card]) -> float | None:
    """The lowest ``outage_pct_min`` any card asks for — the emit threshold (§3)."""
    values = [
        t.conditions.outage_pct_min
        for c in cards
        for t in c.event_triggers
        if t.type is EventType.POWER_OUTAGE and t.conditions.outage_pct_min is not None
    ]
    return min(values) if values else None


def severity_for(pct: float) -> CapSeverity:
    for floor, sev in SEVERITY_BY_PCT:
        if pct >= floor:
            return sev
    return CapSeverity.UNKNOWN


# --------------------------------------------------------------------------- polls → events


def polls_to_events(
    polls: Iterable[OutagePoll],
    customers: dict[str, int],
    *,
    threshold_pct: float,
    poll_minutes: int,
    scenario: str | None = None,
    raw_ref: str | None = None,
) -> list[Event]:
    """One observed ``power_outage`` event per (county, poll) at or above ``threshold_pct``.

    Consecutive polls of one county are contiguous events (``expires`` = next poll), so the
    engine's debounce chain follows them; ``poll_streak`` counts the run of qualifying polls
    within this batch for display. Counties absent from the customer table are skipped and
    reported by the caller through ``skipped_counties``.
    """
    by_county: dict[str, list[OutagePoll]] = {}
    for p in polls:
        by_county.setdefault(p.county_fips, []).append(p)
    events: list[Event] = []
    for fips in sorted(by_county):
        county_customers = customers.get(fips)
        if not county_customers:
            continue
        streak = 0
        for p in sorted(by_county[fips], key=lambda x: x.run_start):
            raw_pct = round(p.customers_out / county_customers * 100, 2)
            pct = min(raw_pct, 100.0)  # a county cannot lose more customers than it has
            if pct < threshold_pct:
                streak = 0
                continue
            streak += 1
            metrics: dict[str, float | int | str] = {
                "customers_out": p.customers_out,
                "county_customers": county_customers,
                "outage_pct": pct,
                "poll_streak": streak,
                "poll_minutes": poll_minutes,
                "temporality_basis": "eagle-i measured customers out",
                "denominator": "moehl_mcc_2022",
            }
            if raw_pct > 100.0:
                metrics["outage_pct_raw"] = raw_pct
                metrics["data_quality_flag"] = "customers_out_exceeds_county_customers"
            metrics.update(p.extra)
            place = f"{p.county_name}, {p.state}" if p.county_name else fips
            events.append(
                Event(
                    source=EventSource.EAGLE_I,
                    source_id=f"{fips}:{p.run_start:%Y-%m-%dT%H%M}",
                    event_type=EventType.POWER_OUTAGE,
                    event_name="Power outage (EAGLE-I)",
                    headline=(
                        f"{place}: {p.customers_out:,} of {county_customers:,} electric "
                        f"customers out ({pct:.1f}%)"
                    ),
                    severity=severity_for(pct),
                    urgency=CapUrgency.IMMEDIATE,
                    certainty=CapCertainty.OBSERVED,
                    temporality=Temporality.OBSERVED,
                    onset=p.run_start,
                    expires=p.run_start + timedelta(minutes=poll_minutes),
                    sent=p.run_start,
                    geography=EventGeography(
                        county_fips=[fips],
                        states=[p.state] if len(p.state) == 2 else [],
                        note="county from EAGLE-I county FIPS",
                    ),
                    metrics=metrics,
                    scenario=scenario,
                    raw_ref=raw_ref,
                )
            )
    return events


def skipped_counties(polls: Iterable[OutagePoll], customers: dict[str, int]) -> list[str]:
    return sorted({p.county_fips for p in polls if not customers.get(p.county_fips)})


# --------------------------------------------------------------------------- live (ArcGIS)


def parse_features(features: list[dict[str, Any]]) -> list[OutagePoll]:
    """ArcGIS ``features[].attributes`` with the EAGLE-I API fields → polls."""
    polls: list[OutagePoll] = []
    for feat in features:
        a = feat.get("attributes") or feat
        try:
            fips = str(a[FIELDS["fips"]]).strip().zfill(5)
            out = int(a[FIELDS["customers_out"]] or 0)
            run_ms = a[FIELDS["run_start"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"EAGLE-I feature lacks expected fields ({exc}): {a}") from exc
        if run_ms is None:
            continue
        run_start = datetime.fromtimestamp(int(run_ms) / 1000, tz=UTC)
        extra = {}
        for key in ("covered_customers", "model_count"):
            v = a.get(FIELDS[key])
            if isinstance(v, int):
                extra[f"feed_{key}"] = v
        polls.append(
            OutagePoll(
                county_fips=fips,
                run_start=run_start,
                customers_out=out,
                county_name=str(a.get(FIELDS["county"]) or ""),
                state=str(a.get(FIELDS["state"]) or ""),
                extra=extra,
            )
        )
    return polls


# Public state mirrors of the EAGLE-I feed with the same fields, verified live 2026-09-22 (the
# only two found with current data). Used when no FEMA token is available.
STATE_MIRRORS: dict[str, str] = {
    "GA": "https://services1.arcgis.com/2iUE8l8JKrP2tygQ/arcgis/rest/services/"
    "Join_Features_to_GEMA_All_Hazards_and_Master_Contacts_Layer_view/FeatureServer/0",
    "OH": "https://services6.arcgis.com/zxOMWqh0yAD6mMsJ/arcgis/rest/services/"
    "power_outages_eagle_i/FeatureServer/0",
}
FEMA_HOST = "gis.fema.gov"
MAX_MIRROR_AGE_HOURS = 6.0


def feature_urls_from_env(value: str | None = None) -> list[str]:
    """``EAGLEI_FEATURE_URL`` may list several layers, separated by commas or whitespace."""
    raw = os.environ.get("EAGLEI_FEATURE_URL", "") if value is None else value
    return [u.strip().rstrip("/") for u in raw.replace(",", " ").split() if u.strip()]


class EagleIProvider(EventProvider):
    """Polls one or more ArcGIS layers carrying the EAGLE-I county fields: FEMA's national
    partner layer (token), or public state mirrors. Each layer is fetched on its own; a
    failing or stale layer is skipped and reported, and the run fails only when no layer
    produced a current snapshot. ``coverage`` and ``notes`` describe the last run for the
    feed-status banner."""

    source = EventSource.EAGLE_I

    def __init__(
        self,
        customers: dict[str, int],
        *,
        threshold_pct: float,
        feature_urls: list[str] | None = None,
        feature_url: str | None = None,
        token: str | None = None,
        raw_dir: Path | None = None,
        poll_minutes: int = LIVE_POLL_MINUTES,
        max_age_hours: float = MAX_MIRROR_AGE_HOURS,
        now: datetime | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.customers = customers
        self.threshold_pct = threshold_pct
        urls = feature_urls or ([feature_url] if feature_url else feature_urls_from_env())
        self.feature_urls = [u.rstrip("/") for u in (urls or [FEMA_FEATURE_URL])]
        self.token = token or os.environ.get("EAGLEI_TOKEN") or None
        self.raw_dir = raw_dir
        self.poll_minutes = poll_minutes
        self.max_age_hours = max_age_hours
        self._now = now
        self.coverage: list[str] = []
        self.notes: list[str] = []
        self._client = httpx.Client(
            headers={"User-Agent": os.environ.get("NWS_USER_AGENT") or "med-extreme-events"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    @property
    def feature_url(self) -> str:  # the first layer, for messages and older callers
        return self.feature_urls[0]

    def close(self) -> None:
        self._client.close()

    def _page(self, url: str, offset: int) -> dict[str, Any]:
        params: dict[str, str] = {
            "where": "1=1",
            # only the outage fields: some mirrors join EAGLE-I to layers holding contact
            # details of emergency managers, which we have no reason to copy
            "outFields": ",".join(FIELDS.values()),
            "returnGeometry": "false",
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE_SIZE),
            "f": "json",
        }
        if self.token and httpx.URL(url).host == FEMA_HOST:
            params["token"] = self.token  # never send a FEMA token to third-party mirrors
        r = self._client.get(f"{url}/query", params=params)
        if r.status_code != 200:
            raise ProviderError(f"EAGLE-I {url}: HTTP {r.status_code} {r.text[:200]}")
        doc: dict[str, Any] = r.json()
        if "error" in doc:
            err = doc["error"]
            hint = (
                " — this ArcGIS service needs a token: set EAGLEI_TOKEN, or point "
                "EAGLEI_FEATURE_URL at a public EAGLE-I mirror with the same fields"
                if err.get("code") in (498, 499)
                else ""
            )
            raise ProviderError(f"EAGLE-I {url}: {err.get('message')}{hint}")
        return doc

    def _layer_features(self, url: str) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = []
        offset = 0
        for _ in range(100):  # a layer that ignores resultOffset must not loop forever
            doc = self._page(url, offset)
            page = doc.get("features", [])
            features.extend(page)
            if not doc.get("exceededTransferLimit") or not page:
                break
            offset += len(page)
        return features

    def fetch_polls(self) -> tuple[list[OutagePoll], str | None]:
        """Latest reading per county across every layer that answered with current data."""
        now = self._now or datetime.now(UTC)
        latest: dict[str, OutagePoll] = {}
        raw: dict[str, list[dict[str, Any]]] = {}
        self.notes = []
        errors: list[str] = []
        for url in self.feature_urls:
            host = httpx.URL(url).host
            try:
                features = self._layer_features(url)
                polls = parse_features(features)
            except (ProviderError, httpx.HTTPError, ValueError) as exc:
                errors.append(str(exc))
                self.notes.append(f"{host}: failed")
                continue
            raw[url] = features
            if not polls:
                self.notes.append(f"{host}: empty")
                continue
            age_h = (now - max(p.run_start for p in polls)).total_seconds() / 3600
            if age_h > self.max_age_hours:
                self.notes.append(f"{host}: stale ({age_h:.0f} h old), skipped")
                continue
            for p in polls:
                cur = latest.get(p.county_fips)
                if cur is None or p.run_start > cur.run_start:
                    latest[p.county_fips] = p
        polls = [latest[k] for k in sorted(latest)]
        self.coverage = sorted({p.state for p in polls if p.state})
        raw_ref = None
        if self.raw_dir is not None and raw:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out = self.raw_dir / f"eaglei_outages_{stamp}.json"
            out.write_text(json.dumps(raw), encoding="utf-8")
            raw_ref = str(out)
        if not polls:
            reason = "; ".join(errors + self.notes) or "no layer answered"
            raise ProviderError(f"EAGLE-I: no current outage snapshot ({reason})")
        return polls, raw_ref

    def status_detail(self, events: int) -> str:
        """One line for the feed banner: coverage, counties polled and what cleared a card."""
        where = ", ".join(self.coverage) or "none"
        kind = (
            "national (FEMA)"
            if any(FEMA_HOST in u for u in self.feature_urls)
            else ("public state mirrors")
        )
        extra = f"; {'; '.join(self.notes)}" if self.notes else ""
        return (
            f"coverage {where} ({kind}); {events} county readings ≥ "
            f"{self.threshold_pct:g}% of customers out{extra}"
        )

    def fetch(self, window: TimeWindow) -> list[Event]:
        """The current snapshot (one run per county); the store accumulates polls over time."""
        polls, raw_ref = self.fetch_polls()
        missing = skipped_counties(polls, self.customers)
        if missing:
            log.warning(
                "EAGLE-I: %d counties have no customer denominator and are skipped: %s",
                len(missing),
                ", ".join(missing[:10]),
            )
        events = polls_to_events(
            polls,
            self.customers,
            threshold_pct=self.threshold_pct,
            poll_minutes=self.poll_minutes,
            raw_ref=raw_ref,
        )
        return [e for e in events if e.expires >= window.start and e.onset <= window.end]


# --------------------------------------------------------------------------- replay (ORNL)


def _ornl_time(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def iter_ornl_csv(
    path: Path,
    *,
    states: set[str] | None = None,
    counties: set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Iterator[OutagePoll]:
    """Stream an ORNL EAGLE-I yearly county CSV (gigabytes for recent years), yielding only
    rows inside the state/county/time slice. ``states`` are full names as the file spells
    them ('Texas'); ``counties`` are 5-digit FIPS."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        count_col = next((c for c in ORNL_COUNT_COLUMNS if c in cols), None)
        if count_col is None or "fips_code" not in cols or "run_start_time" not in cols:
            raise ProviderError(f"{path}: unexpected ORNL columns {cols}")
        for r in reader:
            if states and r["state"] not in states:
                continue
            fips = r["fips_code"].strip().zfill(5)
            if counties and fips not in counties:
                continue
            when = _ornl_time(r["run_start_time"])
            if (start and when < start) or (end and when > end):
                continue
            try:
                out = int(float(r[count_col] or 0))
            except ValueError:
                continue
            yield OutagePoll(
                county_fips=fips,
                run_start=when,
                customers_out=out,
                county_name=r.get("county", ""),
                state=STATE_ABBR.get(r["state"], r["state"]),
            )


def resample_polls(polls: Iterable[OutagePoll], minutes: int) -> list[OutagePoll]:
    """Bucket polls per county into ``minutes``-wide windows keeping the maximum customers
    out (the conservative choice for a health trigger); run_start becomes the bucket start."""
    best: dict[tuple[str, datetime], OutagePoll] = {}
    for p in polls:
        epoch = int(p.run_start.timestamp())
        bucket = datetime.fromtimestamp(epoch - epoch % (minutes * 60), tz=UTC)
        key = (p.county_fips, bucket)
        cur = best.get(key)
        if cur is None or p.customers_out > cur.customers_out:
            best[key] = OutagePoll(
                county_fips=p.county_fips,
                run_start=bucket,
                customers_out=p.customers_out,
                county_name=p.county_name,
                state=p.state,
                extra=dict(p.extra),
            )
    return [best[k] for k in sorted(best)]


def slice_ornl_csv(
    src: Path,
    dest: Path,
    *,
    states: set[str] | None = None,
    counties: set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Write the slice of an ORNL yearly CSV to ``dest`` (normalized columns) so a scenario
    fixture keeps a small raw file instead of the yearly gigabyte. Returns rows written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fips_code", "county", "state", "customers_out", "run_start_time"])
        for p in iter_ornl_csv(src, states=states, counties=counties, start=start, end=end):
            w.writerow(
                [
                    p.county_fips,
                    p.county_name,
                    STATE_NAME.get(p.state, p.state),
                    p.customers_out,
                    p.run_start.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )
            n += 1
    return n


def load_ornl_events(
    path: Path,
    customers: dict[str, int],
    *,
    threshold_pct: float,
    scenario: str,
    raw_ref: str | None = None,
    resample_minutes: int | None = 60,
    states: set[str] | None = None,
    counties: set[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Event]:
    """Replay path: ORNL CSV slice → events. Hourly resampling (max within the hour) is the
    default for fixtures; ``None`` keeps the native 15-minute cadence."""
    polls: list[OutagePoll] = list(
        iter_ornl_csv(path, states=states, counties=counties, start=start, end=end)
    )
    minutes = ORNL_POLL_MINUTES
    if resample_minutes:
        polls = resample_polls(polls, resample_minutes)
        minutes = resample_minutes
    missing = skipped_counties(polls, customers)
    if missing:
        log.warning(
            "EAGLE-I %s: %d counties have no customer denominator and are skipped: %s",
            path.name,
            len(missing),
            ", ".join(missing[:10]),
        )
    return polls_to_events(
        polls,
        customers,
        threshold_pct=threshold_pct,
        poll_minutes=minutes,
        scenario=scenario,
        raw_ref=raw_ref,
    )


STATE_ABBR: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
    "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY", "Puerto Rico": "PR",
    "Guam": "GU", "Virgin Islands": "VI", "U.S. Virgin Islands": "VI", "American Samoa": "AS",
    "Northern Mariana Islands": "MP",
}  # fmt: skip
STATE_NAME = {v: k for k, v in STATE_ABBR.items()}
