"""VA Facilities API v1 parser and paged client (network boundary mocked with httpx)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from xevents.models import Facility, OperatingStatusCode
from xevents.providers.va_facilities import (
    SANDBOX_BASE_URL,
    FacilitiesAPIError,
    VAFacilitiesClient,
    from_geojson,
    parse_page,
    to_geojson,
)

SAMPLE = Path(__file__).parent / "fixtures" / "facilities" / "v1_page_sample.json"


@pytest.fixture(scope="module")
def sample_page() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return doc


@pytest.fixture(scope="module")
def sample_facilities(sample_page: dict[str, Any]) -> list[Facility]:
    return parse_page(sample_page)


def test_parse_sample_page(sample_facilities: list[Facility]) -> None:
    by_id = {f.id: f for f in sample_facilities}
    assert set(by_id) == {"vha_648", "vha_663", "vha_516GC", "vha_999ZZ"}
    portland = by_id["vha_648"]
    assert portland.zip5 == "97239", "ZIP+4 must be normalised to five digits"
    assert portland.visn == "20"
    assert portland.state == "OR"
    assert portland.operating_status is OperatingStatusCode.NORMAL
    assert portland.health_care_system == "VA Portland Health Care System"
    assert (portland.lat, portland.lon) == (45.49707, -122.68344)


def test_numeric_visn_and_status_info(sample_facilities: list[Facility]) -> None:
    seattle = next(f for f in sample_facilities if f.id == "vha_663")
    assert seattle.visn == "20", "numeric visn in payload is normalised to a string"
    assert seattle.operating_status is OperatingStatusCode.NOTICE
    assert seattle.operating_status_info is not None and "Parking" in seattle.operating_status_info


def test_missing_zip_is_none(sample_facilities: list[Facility]) -> None:
    nowhere = next(f for f in sample_facilities if f.id == "vha_999ZZ")
    assert nowhere.zip5 is None
    assert nowhere.operating_status is OperatingStatusCode.TEMPORARY_CLOSURE


def test_geojson_round_trip(sample_facilities: list[Facility]) -> None:
    doc = to_geojson(sample_facilities)
    assert doc["type"] == "FeatureCollection"
    feature = doc["features"][0]
    assert feature["geometry"] == {"type": "Point", "coordinates": [-122.68344, 45.49707]}
    assert "lat" not in feature["properties"]
    assert from_geojson(doc) == sample_facilities


def test_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VA_FACILITIES_API_KEY", raising=False)
    with pytest.raises(FacilitiesAPIError, match="VA_FACILITIES_API_KEY"):
        VAFacilitiesClient()


def test_client_pages_until_total_pages(sample_page: dict[str, Any], tmp_path: Path) -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "test-key"
        assert request.headers["accept"] == "application/json"
        params = dict(request.url.params)
        seen.append(params)
        page = int(params["page"])
        data = sample_page["data"][:2] if page == 1 else sample_page["data"][2:]
        body = {
            "data": data,
            "meta": {"pagination": {"currentPage": page, "perPage": 2, "totalPages": 2}},
        }
        return httpx.Response(200, json=body)

    client = VAFacilitiesClient(
        api_key="test-key", per_page=2, transport=httpx.MockTransport(handler)
    )
    try:
        facilities = client.fetch_all("health", raw_dir=tmp_path)
    finally:
        client.close()
    assert [p["page"] for p in seen] == ["1", "2"]
    assert all(p["type"] == "health" for p in seen)
    assert len(facilities) == 4
    assert len(list(tmp_path.glob("facilities_health_*_p00?.json"))) == 2


def test_client_surfaces_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "No API key found in request"})

    client = VAFacilitiesClient(api_key="bad", transport=httpx.MockTransport(handler))
    with pytest.raises(FacilitiesAPIError, match="HTTP 401"):
        list(client.iter_pages())
    client.close()


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("VA_FACILITIES_API_KEY"), reason="needs VA key")
def test_live_facilities_contract() -> None:
    """Upstream format drift check: one small live page must parse.

    Uses the sandbox host: self-service developer.va.gov keys are sandbox-only.
    """
    client = VAFacilitiesClient(base_url=SANDBOX_BASE_URL, per_page=5)
    try:
        page = next(client.iter_pages("health"))
    finally:
        client.close()
    facilities = parse_page(page)
    assert facilities and all(f.id.startswith("vha_") for f in facilities)
    assert "pagination" in page["meta"]
