"""VA Lighthouse Facilities API v1 client and parser.

Verified 2026-09-20 against the public OpenAPI document
(https://api.va.gov/internal/docs/facilities/v1/openapi.json): v1 has no ``/facilities/all``
and no GeoJSON media type (both were v0, which now 404s). Facilities are pulled with
``GET /facilities?type=health&page=N&per_page=M`` (JSON:API, ``apikey`` header) and paged
via ``meta.pagination``. We build our own GeoJSON.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from xevents.models import Facility, OperatingStatusCode

PRODUCTION_BASE_URL = "https://api.va.gov/services/va_facilities/v1"
SANDBOX_BASE_URL = "https://sandbox-api.va.gov/services/va_facilities/v1"
DEFAULT_USER_AGENT = "med-extreme-events (https://github.com/shlyakhter1/med-extreme-events)"


class FacilitiesAPIError(RuntimeError):
    pass


def _zip5(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = value.strip()[:5]
    return digits if len(digits) == 5 and digits.isdigit() else None


def parse_facility(item: dict[str, Any]) -> Facility:
    """Convert one JSON:API ``data[]`` entry into a ``Facility``."""
    attrs = item.get("attributes") or {}
    address = ((attrs.get("address") or {}).get("physical")) or {}
    status = attrs.get("operatingStatus") or {}
    visn = attrs.get("visn")
    hcs = attrs.get("healthCareSystem") or {}
    return Facility(
        id=str(item["id"]),
        name=str(attrs["name"]),
        facility_type=str(attrs["facilityType"]),
        classification=attrs.get("classification") or None,
        lat=float(attrs["lat"]),
        lon=float(attrs["long"]),
        zip5=_zip5(address.get("zip")),
        city=address.get("city") or None,
        state=address.get("state") or None,
        visn=str(int(visn)) if visn not in (None, "") else None,
        health_care_system=hcs.get("name") or None,
        operating_status=OperatingStatusCode(status.get("code") or "NORMAL"),
        operating_status_info=status.get("additionalInfo") or None,
    )


def parse_page(page: dict[str, Any]) -> list[Facility]:
    return [parse_facility(item) for item in page.get("data", [])]


def to_geojson(facilities: list[Facility]) -> dict[str, Any]:
    """GeoJSON FeatureCollection; properties are the Facility fields minus lat/lon."""
    features = []
    for f in facilities:
        props = f.model_dump(mode="json", exclude={"lat", "lon"})
        features.append(
            {
                "type": "Feature",
                "id": f.id,
                "geometry": {"type": "Point", "coordinates": [f.lon, f.lat]},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def from_geojson(doc: dict[str, Any]) -> list[Facility]:
    out = []
    for feat in doc.get("features", []):
        lon, lat = feat["geometry"]["coordinates"]
        out.append(Facility(lat=lat, lon=lon, **feat["properties"]))
    return out


class VAFacilitiesClient:
    """Thin paged client. ``api_key`` defaults to ``VA_FACILITIES_API_KEY``."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = PRODUCTION_BASE_URL,
        *,
        per_page: int = 500,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        key = api_key or os.environ.get("VA_FACILITIES_API_KEY")
        if not key:
            raise FacilitiesAPIError("VA_FACILITIES_API_KEY is not set (free at developer.va.gov)")
        self.per_page = per_page
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                "apikey": key,
                "Accept": "application/json",
                "User-Agent": os.environ.get("NWS_USER_AGENT") or DEFAULT_USER_AGENT,
            },
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def iter_pages(self, facility_type: str = "health") -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            r = self._client.get(
                "/facilities",
                params={"type": facility_type, "page": page, "per_page": self.per_page},
            )
            if r.status_code != 200:
                raise FacilitiesAPIError(
                    f"GET /facilities page {page}: HTTP {r.status_code} {r.text[:200]}"
                )
            doc: dict[str, Any] = r.json()
            yield doc
            pagination = (doc.get("meta") or {}).get("pagination") or {}
            total_pages = int(pagination.get("totalPages") or 1)
            if page >= total_pages or not doc.get("data"):
                return
            page += 1

    def fetch_all(
        self, facility_type: str = "health", raw_dir: Path | None = None
    ) -> list[Facility]:
        """Pull every facility of ``facility_type``; optionally save each raw page."""
        facilities: list[Facility] = []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        for i, page in enumerate(self.iter_pages(facility_type), start=1):
            if raw_dir is not None:
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"facilities_{facility_type}_{stamp}_p{i:03d}.json").write_text(
                    json.dumps(page, indent=1), encoding="utf-8"
                )
            facilities.extend(parse_page(page))
        return facilities
