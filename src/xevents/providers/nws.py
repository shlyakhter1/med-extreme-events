"""NWS alerts provider (api.weather.gov ``/alerts/active``) and CAP → Event normalization.

Etiquette: a User-Agent with contact info is mandatory (``NWS_USER_AGENT``). We request
``status=actual`` and filter to the event vocabulary the cards use. Geography: CAP ``SAME``
codes give county FIPS directly; UGC zones resolve through the zone-county correlation.
"""

from __future__ import annotations

import json
import os
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
    EventType,
    TimeWindow,
)
from xevents.providers.base import EventProvider, ProviderError

BASE_URL = "https://api.weather.gov"

# NWS `event` → our event type. Anything not listed is ignored by the provider.
NWS_EVENT_TYPES: dict[str, EventType] = {
    "Excessive Heat Warning": EventType.HEAT,
    "Extreme Heat Warning": EventType.HEAT,
    "Excessive Heat Watch": EventType.HEAT,
    "Extreme Heat Watch": EventType.HEAT,
    "Heat Advisory": EventType.HEAT,
    "Hurricane Watch": EventType.HURRICANE_FLOOD,
    "Hurricane Warning": EventType.HURRICANE_FLOOD,
    "Tropical Storm Watch": EventType.HURRICANE_FLOOD,
    "Tropical Storm Warning": EventType.HURRICANE_FLOOD,
    "Storm Surge Watch": EventType.HURRICANE_FLOOD,
    "Storm Surge Warning": EventType.HURRICANE_FLOOD,
    "Flood Watch": EventType.HURRICANE_FLOOD,
    "Flood Warning": EventType.HURRICANE_FLOOD,
    "Flash Flood Warning": EventType.HURRICANE_FLOOD,
    "Flash Flood Watch": EventType.HURRICANE_FLOOD,
    "Air Quality Alert": EventType.AIR_POLLUTION,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(UTC)


def _enum(cls: type[Any], value: Any, default: Any) -> Any:
    try:
        return cls(value)
    except (ValueError, TypeError):
        return default


def parse_alert(
    feature: dict[str, Any], resolver: UgcResolver, raw_ref: str | None = None
) -> Event | None:
    """One CAP GeoJSON feature → Event, or None if the event type is not one we track."""
    p = feature.get("properties") or {}
    event_type = NWS_EVENT_TYPES.get(p.get("event", ""))
    if event_type is None:
        return None
    geocode = p.get("geocode") or {}
    ugcs = list(geocode.get("UGC") or [])
    counties, note = resolver.resolve(ugcs, geocode.get("SAME") or [])
    onset = _parse_dt(p.get("onset")) or _parse_dt(p.get("effective")) or _parse_dt(p.get("sent"))
    expires = _parse_dt(p.get("ends")) or _parse_dt(p.get("expires"))
    if onset is None or expires is None:
        raise ProviderError(f"alert {p.get('id')} lacks onset/expires")
    if expires < onset:
        expires = onset
    states = sorted({u[:2] for u in ugcs})
    return Event(
        source=EventSource.NWS,
        source_id=str(p["id"]),
        event_type=event_type,
        event_name=str(p["event"]),
        headline=p.get("headline") or None,
        severity=_enum(CapSeverity, p.get("severity"), CapSeverity.UNKNOWN),
        urgency=_enum(CapUrgency, p.get("urgency"), CapUrgency.UNKNOWN),
        certainty=_enum(CapCertainty, p.get("certainty"), CapCertainty.UNKNOWN),
        onset=onset,
        expires=expires,
        sent=_parse_dt(p.get("sent")),
        geography=EventGeography(
            county_fips=counties,
            ugc=ugcs,
            states=states,
            polygon=feature.get("geometry") or None,
            area_desc=p.get("areaDesc") or None,
            note=note,
        ),
        metrics={
            "message_type": str(p.get("messageType") or ""),
            "sender": str(p.get("senderName") or ""),
        },
        raw_ref=raw_ref,
    )


def parse_alerts(
    doc: dict[str, Any], resolver: UgcResolver, raw_ref: str | None = None
) -> list[Event]:
    events = []
    for feature in doc.get("features", []):
        ev = parse_alert(feature, resolver, raw_ref)
        if ev is not None:
            events.append(ev)
    return events


class NWSAlertsProvider(EventProvider):
    source = EventSource.NWS

    def __init__(
        self,
        resolver: UgcResolver,
        *,
        user_agent: str | None = None,
        base_url: str = BASE_URL,
        raw_dir: Path | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        ua = user_agent or os.environ.get("NWS_USER_AGENT")
        if not ua:
            raise ProviderError("NWS_USER_AGENT is not set (NWS requires a contact string)")
        self.resolver = resolver
        self.raw_dir = raw_dir
        self._client = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": ua, "Accept": "application/geo+json"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def fetch(self, window: TimeWindow) -> list[Event]:
        """Active alerts (the API keeps no history), filtered to those overlapping ``window``."""
        r = self._client.get("/alerts/active", params={"status": "actual"})
        if r.status_code != 200:
            raise ProviderError(f"GET /alerts/active: HTTP {r.status_code} {r.text[:200]}")
        doc: dict[str, Any] = r.json()
        raw_ref = None
        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            path = self.raw_dir / f"nws_alerts_active_{stamp}.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            raw_ref = str(path)
        events = parse_alerts(doc, self.resolver, raw_ref)
        return [e for e in events if e.expires >= window.start and e.onset <= window.end]
