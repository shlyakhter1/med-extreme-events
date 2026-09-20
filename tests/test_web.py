"""Server-rendered pages: dashboard, facility drill-down, role toggle, acknowledge, patient view."""

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
AT = "2021-06-28T00:00:00+00:00"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    eng: Engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('web') / 'web.db'}")
    init_db(eng)
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    facilities = attribute_facilities(raw, ZipCountyCrosswalk.load(), CountyIndex.load()).facilities
    upsert_facilities(eng, facilities)
    profile = load_profile(PROFILES_DIR / "va.yaml")
    cards = load_cards(CARDS_DIR)

    def panels(fid: str, card: Card) -> Estimate:
        return Estimate(label="p", value=123.0, formula="veterans × rate (test)", inputs={})

    for name in ("heat_dome_2021", "ian_2022"):
        events = load_scenario(name)
        upsert_events(eng, events)
        result = match(
            events, cards, facilities, profile, panels, now=datetime(2026, 1, 1, tzinfo=UTC)
        )
        upsert_action_items(eng, result.items)
    return TestClient(create_app(eng))


def test_dashboard_replay_heat_dome(client: TestClient) -> None:
    r = client.get("/", params={"scenario": "heat_dome_2021", "at": AT})
    assert r.status_code == 200
    html = r.text
    assert "Event board" in html and "Portland VA Medical Center" in html
    assert "Excessive Heat Warning" in html
    assert "Replay" in html and "heat_dome_2021" in html
    assert "/dashboard/facilities/vha_648" in html


def test_dashboard_defaults_to_peak_hour(client: TestClient) -> None:
    r = client.get("/", params={"scenario": "ian_2022"})
    assert r.status_code == 200
    assert "Bay Pines" in r.text or "Orlando" in r.text or "Tampa" in r.text
    assert 'value="2022-09-2' in r.text  # as-of defaulted inside the scenario window


def test_dashboard_live_mode_has_freshness_banner(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Live mode" in r.text and "no live events ingested yet" in r.text
    assert "absence of items is not an all-clear" in r.text
    assert client.get("/", params={"scenario": "nope"}).status_code == 404


def test_facility_page_roles_and_acknowledge(client: TestClient) -> None:
    r = client.get("/dashboard/facilities/vha_648", params={"scenario": "heat_dome_2021", "at": AT})
    assert r.status_code == 200
    html = r.text
    assert "Extreme Heat × Bipolar Disorder on Lithium" in html
    assert "Generate the lithium roster" in html, "clinician checklist rendered verbatim"
    assert "how was this number computed?" in html and "veterans × rate (test)" in html
    assert "Acknowledge" in html
    patient = client.get(
        "/dashboard/facilities/vha_648/cards",
        params={"scenario": "heat_dome_2021", "at": AT, "role": "patient"},
    )
    assert patient.status_code == 200
    assert "Heat can push your lithium to a dangerous level." in patient.text
    assert "stop your medication" in patient.text  # apostrophe is HTML-escaped
    caregiver = client.get(
        "/dashboard/facilities/vha_648/cards",
        params={"scenario": "heat_dome_2021", "at": AT, "role": "caregiver"},
    )
    assert "No caregiver content" in caregiver.text
    item_id = html.split('hx-post="/dashboard/action-items/')[1].split("/status")[0]
    ack = client.post(
        f"/dashboard/action-items/{item_id}/status", params={"status": "acknowledged"}
    )
    assert ack.status_code == 200 and "acknowledged" in ack.text
    again = client.get(
        "/dashboard/facilities/vha_648", params={"scenario": "heat_dome_2021", "at": AT}
    )
    assert "Mark completed" in again.text
    assert (
        client.post(
            f"/dashboard/action-items/{item_id}/status", params={"status": "issued"}
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/dashboard/facilities/vha_nope", params={"scenario": "heat_dome_2021"}
        ).status_code
        == 404
    )


def test_patient_view(client: TestClient) -> None:
    r = client.get(
        "/demo/patient-view",
        params={
            "facility": "vha_648",
            "card": "heat-lithium",
            "scenario": "heat_dome_2021",
            "at": AT,
        },
    )
    assert r.status_code == 200
    assert "Heat can push your lithium to a dangerous level." in r.text
    assert "Call right away if you notice" in r.text
    assert "Generate the lithium roster" not in r.text, "no clinician text in the patient view"
    assert "decision support for contacting your care team" in r.text
    cg = client.get(
        "/demo/patient-view",
        params={"facility": "vha_648", "scenario": "heat_dome_2021", "at": AT, "role": "caregiver"},
    )
    assert cg.status_code == 200 and "No caregiver guidance" in cg.text
    assert (
        client.get(
            "/demo/patient-view",
            params={"facility": "vha_648", "card": "nope", "scenario": "heat_dome_2021"},
        ).status_code
        == 404
    )
    assert client.get("/demo/patient-view", params={"facility": "vha_nope"}).status_code == 404


def test_feeds_and_scenario_peak(client: TestClient) -> None:
    feeds = client.get("/feeds").json()
    assert feeds["feeds"] == [] and feeds["stale_after_hours"] == 6.0
    scen = client.get("/scenarios").json()
    heat = next(s for s in scen if s["id"] == "heat_dome_2021")
    assert heat["window_start"] <= heat["peak_at"] <= heat["window_end"]
