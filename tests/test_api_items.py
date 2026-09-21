"""API: scenarios, events, action items (with status changes), cards, reference, playback page."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from xevents.api import create_app
from xevents.cards import CARDS_DIR, load_cards
from xevents.engine import match
from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.models import Card, Estimate
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.replay import load_scenario
from xevents.providers.va_facilities import from_geojson
from xevents.store import (
    init_db,
    make_engine,
    upsert_action_items,
    upsert_events,
    upsert_facilities,
)

REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"
pytestmark = pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    eng: Engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('api') / 'api.db'}")
    init_db(eng)
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    facilities = attribute_facilities(raw, ZipCountyCrosswalk.load(), CountyIndex.load()).facilities
    upsert_facilities(eng, facilities)
    events = load_scenario("heat_dome_2021")
    upsert_events(eng, events)
    profile = load_profile(PROFILES_DIR / "va.yaml")

    def panels(fid: str, card: Card) -> Estimate:
        return Estimate(label="p", value=42.0, formula="test", inputs={})

    result = match(
        events,
        load_cards(CARDS_DIR),
        facilities,
        profile,
        panels,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    upsert_action_items(eng, result.items)
    return TestClient(create_app(eng))


def test_scenarios(client: TestClient) -> None:
    rows = client.get("/scenarios").json()
    assert [r["id"] for r in rows] == ["heat_dome_2021", "ian_2022", "smoke_nyc_2023"]
    heat = rows[0]
    assert heat["events"] == 20 and heat["event_types"] == ["heat"]
    assert heat["window_start"] < heat["window_end"]


def test_events_at_time(client: TestClient) -> None:
    doc = client.get(
        "/events", params={"scenario": "heat_dome_2021", "at": "2021-06-28T00:00:00Z"}
    ).json()
    assert doc["count"] > 0
    names = {e["event_name"] for e in doc["events"]}
    assert "Excessive Heat Warning" in names
    assert all("polygon" not in e["geography"] for e in doc["events"])
    assert (
        client.get(
            "/events", params={"scenario": "heat_dome_2021", "at": "2020-01-01T00:00:00Z"}
        ).json()["count"]
        == 0
    )
    assert client.get("/events", params={"at": "not-a-date"}).status_code == 422
    live = client.get("/events/active").json()
    assert live["count"] == 0 and "as_of" in live


def test_action_items_compact_and_detail(client: TestClient) -> None:
    doc = client.get(
        "/action-items", params={"scenario": "heat_dome_2021", "at": "2021-06-28T00:00:00Z"}
    ).json()
    assert doc["count"] > 0
    row = doc["items"][0]
    assert {
        "id",
        "event_key",
        "card_id",
        "facility_id",
        "role",
        "status",
        "acuity_rank",
        "panel",
        "window_start",
    } <= set(row)
    assert "actions" not in row, "compact rows omit card text"
    assert row["status"] == "issued"
    detail = client.get(f"/action-items/{row['id']}").json()
    assert detail["id"] == row["id"] and detail["actions"] and detail["escalation"]
    assert detail["panel"]["value"] == 42.0
    superseded = client.get(
        "/action-items",
        params={"scenario": "heat_dome_2021", "include_superseded": "true", "status": "superseded"},
    ).json()
    assert superseded["count"] > 0
    assert client.get("/action-items/nope|x|y|z").status_code == 404


def test_facility_action_items_and_status_machine(client: TestClient) -> None:
    doc = client.get(
        "/facilities/vha_648/action-items", params={"scenario": "heat_dome_2021", "role": "patient"}
    ).json()
    assert doc["count"] > 0
    item = doc["items"][0]
    assert item["role"] == "patient" and item["message"]
    iid = item["id"]
    r = client.post(f"/action-items/{iid}/status", json={"status": "acknowledged"})
    assert (
        r.status_code == 200
        and r.json()["status"] == "acknowledged"
        and r.json()["acknowledged_at"]
    )
    assert client.post(f"/action-items/{iid}/status", json={"status": "issued"}).status_code == 409
    assert client.post(f"/action-items/{iid}/status", json={"status": "bogus"}).status_code == 422
    assert client.post("/action-items/nope/status", json={"status": "delivered"}).status_code == 404


def test_events_carry_event_key(client: TestClient) -> None:
    """event_key is a Python property, so model_dump() drops it; clients key on it."""
    doc = client.get("/events", params={"scenario": "heat_dome_2021"}).json()
    assert doc["count"] > 0
    keys = [e.get("event_key") for e in doc["events"]]
    assert all(k and k.startswith("nws:") for k in keys), keys[:3]
    detail = client.get("/events/detail", params={"key": keys[0]}).json()
    assert detail["event_key"] == keys[0]
    assert "polygon" in detail["geography"], "the detail view keeps the polygon"
    assert client.get("/events/detail", params={"key": "nws:nope"}).status_code == 404


def test_pages_have_no_external_asset_dependencies(client: TestClient) -> None:
    """The demo must render with no CDN: assets are vendored and cache-busted."""
    for path in ("/", "/playback"):
        html = client.get(path).text
        assert "unpkg.com" not in html and "cartocdn" not in html, path
        assert "/static/vendor/leaflet.js?v=" in html, path
    for asset in (
        "/static/vendor/leaflet.js",
        "/static/vendor/leaflet.css",
        "/static/vendor/htmx.min.js",
        "/static/map.js",
        "/static/playback.js",
    ):
        r = client.get(asset)
        assert r.status_code == 200 and len(r.content) > 1000, asset


def test_cards_reference_and_playback(client: TestClient) -> None:
    cards = client.get("/cards").json()
    assert len(cards) == 8 and cards[0]["id"] == "heat-lithium"
    r = client.get("/reference/counties")
    assert r.status_code == 200 and r.json()["type"] == "FeatureCollection"
    page = client.get("/playback")
    assert page.status_code == 200
    assert "<title>Playback · med-extreme-events</title>" in page.text
    assert 'id="timeline"' in page.text, "the scrubbable timeline is the point of the page"
    js = client.get("/static/playback.js")
    assert js.status_code == 200 and "activeItems" in js.text
    assert client.get("/static/map.js").status_code == 200
