"""Archived NWS watch/warning/advisory records (Iowa Environmental Mesonet VTEC archive)
→ the same Event model the live NWS provider produces. Used only by scenario builders.

Source: https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py?accept=csv
Rows are per (WFO, phenomena, significance, event id, UGC, status update). We group by the
VTEC event identity, take the earliest issue and latest expiry, and resolve UGCs to counties
with a resolver appropriate to the scenario's date (zone numbering changes over time).
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from xevents.geography.nws_zones import UgcResolver
from xevents.models import (
    CapCertainty,
    CapSeverity,
    CapUrgency,
    Event,
    EventGeography,
    EventSource,
    TimeWindow,
)
from xevents.providers.base import EventProvider, ProviderError
from xevents.providers.nws import NWS_EVENT_TYPES, normalize_nws_event, nws_temporality

BASE_URL = "https://mesonet.agron.iastate.edu"
WATCHWARN = "/cgi-bin/request/gis/watchwarn.py"

# VTEC phenomena.significance → NWS product name (only the products the cards use).
VTEC_NAMES: dict[str, str] = {
    "EH.W": "Excessive Heat Warning",
    "EH.A": "Excessive Heat Watch",
    "XH.W": "Extreme Heat Warning",
    "XH.A": "Extreme Heat Watch",
    "HT.Y": "Heat Advisory",
    "HU.W": "Hurricane Warning",
    "HU.A": "Hurricane Watch",
    "TR.W": "Tropical Storm Warning",
    "TR.A": "Tropical Storm Watch",
    "SS.W": "Storm Surge Warning",
    "SS.A": "Storm Surge Watch",
    "FF.W": "Flash Flood Warning",
    "FF.A": "Flash Flood Watch",
    "FA.A": "Flood Watch",
    "FA.W": "Flood Warning",
    "AQ.Y": "Air Quality Alert",
}
SEVERITY: dict[str, CapSeverity] = {
    "W": CapSeverity.SEVERE,
    "A": CapSeverity.MODERATE,
    "Y": CapSeverity.MINOR,
}


def _dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def parse_iem_csv(
    path: Path,
    resolver: UgcResolver,
    *,
    scenario: str | None,
    states: set[str] | None = None,
    raw_ref: str | None = None,
) -> list[Event]:
    groups: dict[tuple[str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"ugcs": set(), "issue": None, "expire": None, "statuses": set(), "products": set()}
    )
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["gtype"] != "C":
                continue
            ugc = r["ugc"].strip()
            if not ugc or (states and ugc[:2] not in states):
                continue
            ph_sig = f"{r['phenomena']}.{r['significance']}"
            if ph_sig not in VTEC_NAMES:
                continue
            key = (r["vtec_year"], r["wfo"], r["phenomena"], r["significance"], r["eventid"])
            g = groups[key]
            g["ugcs"].add(ugc)
            issue, expire = _dt(r["utc_issue"]), _dt(r["utc_expire"])
            g["issue"] = issue if g["issue"] is None else min(g["issue"], issue)
            g["expire"] = expire if g["expire"] is None else max(g["expire"], expire)
            g["statuses"].add(r["status"])
            g["products"].add(r["product_id"])
    events = []
    for (year, wfo, ph, sig, eid), g in sorted(groups.items()):
        name, legacy_name = normalize_nws_event(VTEC_NAMES[f"{ph}.{sig}"])
        ugcs = sorted(g["ugcs"])
        counties, note = resolver.resolve(ugcs)
        onset, expires = g["issue"], g["expire"]
        # The archive records issued products, not observations: CAP certainty is unknown
        # here, so temporality comes from the product suffix alone.
        temporality, basis = nws_temporality(name, CapCertainty.LIKELY)
        metrics: dict[str, float | int | str] = {
            "vtec": f"{ph}.{sig}",
            "wfo": wfo,
            "statuses": ",".join(sorted(g["statuses"])),
            "product_count": len(g["products"]),
            "retrieval": "iem_vtec_archive",
            "temporality_basis": basis,
        }
        if legacy_name is not None:
            metrics["raw_nws_event"] = legacy_name
        events.append(
            Event(
                source=EventSource.NWS,
                source_id=f"{year}-K{wfo}-{ph}.{sig}-{int(eid):04d}",
                event_type=NWS_EVENT_TYPES[name],
                event_name=name,
                headline=f"{name} (NWS {wfo}, VTEC {ph}.{sig} #{eid}, {year})",
                severity=SEVERITY.get(sig, CapSeverity.UNKNOWN),
                urgency=CapUrgency.EXPECTED,
                certainty=CapCertainty.LIKELY,
                temporality=temporality,
                onset=onset,
                expires=max(expires, onset),
                sent=onset,
                geography=EventGeography(
                    county_fips=counties,
                    ugc=ugcs,
                    states=sorted({u[:2] for u in ugcs}),
                    note=f"IEM VTEC archive; {note}",
                ),
                metrics=metrics,
                scenario=scenario,
                raw_ref=raw_ref,
            )
        )
    return events


def resolver_from_zone_geojson(
    geojson_paths: list[Path], counties: Any, base: UgcResolver | None = None
) -> UgcResolver:
    """Build a UGC resolver from dated zone geometries (IEM ``/api/1/nws/ugcs.geojson``)
    by approximate polygon coverage — needed when a scenario predates the current NWS
    zone-county file (zones get renumbered)."""
    import json

    from xevents.geography.polygons import counties_covered

    zones: dict[str, list[str]] = {}
    for path in geojson_paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for feat in doc.get("features", []):
            ugc = feat["properties"]["ugc"]
            if ugc[2] != "Z" or ugc in zones:
                continue
            covered = counties_covered(feat["geometry"], counties)
            if covered:
                zones[ugc] = covered
    if base is not None:  # dated geometry wins; current file fills gaps
        for ugc, fips in base.zone_map().items():
            zones.setdefault(ugc, fips)
    return UgcResolver(zones)


class IEMArchiveProvider(EventProvider):
    """Recent NWS watch/warning/advisory history from the IEM VTEC archive.

    ``api.weather.gov/alerts/active`` only reports what is in force *right now*, so a live
    view built on it alone shows an empty map the moment the weather calms down. This
    provider backfills the trailing window (two weeks by default) with the same NWS products,
    normalised into the same ``Event`` model. Events stay ``source=nws`` because they are NWS
    products; ``metrics.retrieval`` records that they came from the archive rather than CAP.
    """

    source = EventSource.NWS
    PHENOMENA = "EH,XH,HT,HU,TR,SS,FF,FA"
    SIGNIFICANCE = "W,A,Y"

    def __init__(
        self,
        resolver: UgcResolver,
        *,
        base_url: str = BASE_URL,
        raw_dir: Path | None = None,
        timeout: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.resolver = resolver
        self.raw_dir = raw_dir
        ua = os.environ.get("NWS_USER_AGENT") or "med-extreme-events"
        self._client = httpx.Client(
            base_url=base_url, headers={"User-Agent": ua}, timeout=timeout, transport=transport
        )

    def close(self) -> None:
        self._client.close()

    def fetch(self, window: TimeWindow) -> list[Event]:
        params = {
            "accept": "csv",
            "sts": window.start.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ"),
            "ets": window.end.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ"),
            "phenomena": self.PHENOMENA,
            "significance": self.SIGNIFICANCE,
            "limit1": "no",
        }
        r = self._client.get(WATCHWARN, params=params)
        if r.status_code != 200:
            raise ProviderError(f"IEM archive: HTTP {r.status_code} {r.text[:200]}")
        raw_dir = self.raw_dir or Path(os.environ.get("TMPDIR", "/tmp"))
        raw_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = raw_dir / f"iem_watchwarn_{stamp}.csv"
        path.write_bytes(r.content)
        events = parse_iem_csv(path, self.resolver, scenario=None, raw_ref=str(path))
        return [e for e in events if e.expires >= window.start and e.onset <= window.end]
