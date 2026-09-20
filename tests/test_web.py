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
    # Patient and caregiver are one audience: the caregiver note sits with the patient text
    # rather than behind a separate view.
    assert "whoever is helping them" in r.text
    assert "Switch to caregiver" not in r.text
    assert (
        client.get(
            "/demo/patient-view",
            params={"facility": "vha_648", "card": "nope", "scenario": "heat_dome_2021"},
        ).status_code
        == 404
    )
    assert client.get("/demo/patient-view", params={"facility": "vha_nope"}).status_code == 404


def test_form_submitted_timestamp_is_accepted(client: TestClient) -> None:
    """A browser GET form encodes '+' as a space, so the page used to reject its own
    as-of value with 'bad timestamp'. Every accepted spelling must round-trip."""
    for value in (
        "2021-06-28T00:00:00 00:00",  # what the form actually submits
        "2021-06-28T00:00:00+00:00",
        "2021-06-28T00:00:00Z",
        "2021-06-28T00:00",  # datetime-local
        "2021-06-28",
    ):
        r = client.get("/", params={"scenario": "heat_dome_2021", "at": value})
        assert r.status_code == 200, f"{value!r} → {r.status_code} {r.text[:120]}"
    assert client.get("/", params={"at": "nonsense"}).status_code == 422
    # the header control must emit a value the form can submit back unchanged
    html = client.get("/", params={"scenario": "heat_dome_2021", "at": "2021-06-28T00:00"}).text
    assert 'type="datetime-local" name="at" value="2021-06-28T00:00"' in html


def test_events_pages(client: TestClient) -> None:
    base = {"scenario": "heat_dome_2021", "at": AT}
    r = client.get("/dashboard/events", params=base)
    assert r.status_code == 200
    assert "Excessive Heat Warning" in r.text
    assert "2021-06-2" in r.text, "events must show their timestamps"
    all_events = client.get("/dashboard/events", params={**base, "window": "all"})
    assert all_events.text.count("<tr>") > r.text.count("<tr>")
    key = r.text.split("/dashboard/events/")[1].split("?")[0]
    detail = client.get(f"/dashboard/events/{key}", params=base)
    assert detail.status_code == 200
    assert "Affected counties" in detail.text and "Action items produced" in detail.text
    assert client.get("/dashboard/events/nws:nope", params=base).status_code == 404


def test_events_show_location_and_timestamps(client: TestClient) -> None:
    base = {"scenario": "ian_2022", "at": "2022-09-27T16:00"}
    html = client.get("/dashboard/events", params=base).text
    assert "<th>Where</th>" in html and "<th>Onset (UTC)</th>" in html
    assert "2022-09-2" in html, "timestamps are rendered"
    assert "FL" in html, "location is rendered"
    dash = client.get("/", params=base).text
    assert "<th>Where</th>" in dash


def test_playback_offers_live_and_navigation(client: TestClient) -> None:
    """You must be able to get from playback back to live without editing the URL."""
    html = client.get("/playback").text
    assert 'id="nav-dashboard"' in html and 'id="nav-events"' in html
    assert 'id="scenario"' in html
    js = client.get("/static/playback.js").text
    assert 'value="live"' in js, "the view selector offers live"
    assert "Cards firing now" in js, "cards are surfaced in playback, not only on the dashboard"
    assert "selectCard" in js and "cardColor" in js, "cards can be selected and shown on the map"
    assert client.get("/playback", params={"scenario": "ian_2022"}).status_code == 200


def test_playback_shows_card_content_and_map_symbols(client: TestClient) -> None:
    """Selecting a card must show the card itself, and cards need their own map symbol —
    a fanned chip stack — so they are not confused with the circular facility markers."""
    js = client.get("/static/playback.js").text
    for piece in ("renderCardDetail", "loadCardSample", "drawBadges", "badgeHtml", "renderLegend"):
        assert piece in js, piece
    assert "facilities firing this card" in js, "card detail lists where it is firing"
    assert "escalation triggers" in js and "sources (" in js, "card detail carries provenance"
    assert 'data-role="' in js, "card detail has the care team / patient / caregiver toggle"
    assert "/cards" in js, "card text comes from the card library, not from strings in JS"

    page = client.get("/playback").text
    assert 'id="card-legend"' in page, "the map needs a card legend"
    for rule in (".card-badge .cards i", ".card-badge .cards.one i", "#card-legend"):
        assert rule in page, rule


def test_card_definitions_available_for_the_playback_panel(client: TestClient) -> None:
    cards = client.get("/cards").json()
    assert len(cards) == 6
    by_id = {c["id"]: c for c in cards}
    lithium = by_id["heat-lithium"]
    assert lithium["actions"]["patient"][0]["text"].startswith("Heat can push your lithium")
    assert lithium["sources"] and lithium["evidence_tier"]
    assert lithium["window_days"] == {"min": 3, "max": 7}
    assert {c["number"] for c in cards} == set(range(1, 7)), "stable colours key off card number"


def test_carbon_panel_on_the_facility_page(client: TestClient) -> None:
    base = {"scenario": "heat_dome_2021", "at": AT}
    html = client.get("/dashboard/facilities/vha_648", params=base).text
    assert "carbon footprint of this card's therapies" in html
    assert "Lithium carbonate" in html and "900 mg/day PO" in html
    assert "never for clinical decisions" in html, "the disclaimer travels with the numbers"
    assert "must not be added together" in html, "alternatives are scenarios, not a sum"
    assert "Panel t CO₂e/yr" in html

    doc = client.get("/carbon").json()
    assert len(doc["entries"]) >= 12
    assert set(doc["by_card"]) == {"1", "2", "3", "4", "5", "6"}
    assert doc["by_card"]["6"][0]["citations"], "API rows carry their citations"
    assert "ui_disclaimer" in doc


def test_playback_carbon_and_two_audiences(client: TestClient) -> None:
    js = client.get("/static/playback.js").text
    assert "carbonBlock" in js and "ui_disclaimer" in js
    assert "must not be added together" in js
    assert 'label: "patient & caregiver"' in js, "patient and caregiver are one audience"
    assert '"/carbon"' in js
    # the detail panel must sit above the long lists or a selection is never seen
    detail = js.index('`<div id="detail"></div>`')
    cards_heading = js.index("Cards firing now")
    facilities_heading = js.index("Facilities by acuity")
    assert detail < cards_heading < facilities_heading


def test_feeds_and_scenario_peak(client: TestClient) -> None:
    feeds = client.get("/feeds").json()
    assert feeds["feeds"] == [] and feeds["stale_after_hours"] == 6.0
    scen = client.get("/scenarios").json()
    heat = next(s for s in scen if s["id"] == "heat_dome_2021")
    assert heat["window_start"] <= heat["peak_at"] <= heat["window_end"]
