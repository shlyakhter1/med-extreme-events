"""Facility persistence (SQLite) and the /facilities map endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from xevents.api import create_app
from xevents.geography import ZipCountyCrosswalk, attribute_facilities
from xevents.providers.va_facilities import parse_page
from xevents.store import get_facility, init_db, list_facilities, make_engine, upsert_facilities

SAMPLE = Path(__file__).parent / "fixtures" / "facilities" / "v1_page_sample.json"


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(eng)
    facilities = parse_page(json.loads(SAMPLE.read_text(encoding="utf-8")))
    report = attribute_facilities(facilities, ZipCountyCrosswalk.load())
    upsert_facilities(eng, report.facilities)
    return eng


def test_upsert_is_idempotent(engine: Engine) -> None:
    before = list_facilities(engine)
    upsert_facilities(engine, before)
    after = list_facilities(engine)
    assert after == before
    assert len(after) == 4


def test_filters(engine: Engine) -> None:
    assert {f.id for f in list_facilities(engine, state="wa")} == {"vha_663"}
    assert {f.id for f in list_facilities(engine, visn="20")} == {"vha_648", "vha_663"}
    assert {f.id for f in list_facilities(engine, county_fips="12071")} == {"vha_516GC"}
    assert get_facility(engine, "vha_648") is not None
    assert get_facility(engine, "vha_nope") is None


def test_map_endpoint_returns_geojson(engine: Engine) -> None:
    client = TestClient(create_app(engine))
    r = client.get("/facilities")
    assert r.status_code == 200
    doc = r.json()
    assert doc["type"] == "FeatureCollection"
    assert len(doc["features"]) == 4
    portland = next(f for f in doc["features"] if f["id"] == "vha_648")
    assert portland["geometry"]["coordinates"] == [-122.68344, 45.49707]
    assert portland["properties"]["county_fips"] == "41051"
    assert portland["properties"]["visn"] == "20"
    assert portland["properties"]["operating_status"] == "NORMAL"


def test_map_endpoint_filters_and_404(engine: Engine) -> None:
    client = TestClient(create_app(engine))
    assert [
        f["id"] for f in client.get("/facilities", params={"state": "FL"}).json()["features"]
    ] == ["vha_516GC"]
    assert client.get("/facilities", params={"county": "1207"}).status_code == 422
    assert (
        client.get("/facilities/vha_663").json()["properties"]["name"]
        == "Seattle VA Medical Center"
    )
    assert client.get("/facilities/vha_nope").status_code == 404
    assert client.get("/health").json()["status"] == "ok"
