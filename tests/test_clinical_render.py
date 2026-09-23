"""The clinical review's rendering rules (implementation-plan-clinical M12 §3–§5): planning
estimates are labeled as such, both Card 6 hotlines are tappable, caveats (where the contested
findings live) render, and no page shows library markup."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from xevents.api import create_app
from xevents.cards import CARDS_DIR, load_cards
from xevents.denominators import ESTIMATE_KIND_LABELS, PLANNING_CAVEAT
from xevents.engine import match
from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.models import Card, Estimate, EstimateKind
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
from xevents.web.views import tel_links

REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"
pytestmark = pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")
IAN = {"scenario": "ian_2022", "at": "2022-09-29T00:00:00+00:00"}
KHARES = '<a href="tel:+18664463507">866-446-3507</a>'
KCER = '<a href="tel:+18669013773">1-866-901-3773</a>'


def _panel(fid: str, card: Card) -> Estimate:
    """A planning-estimate panel with a measured component, as Card 6 has in production."""
    measured = Estimate(
        label="DME (sub-panel)",
        value=40.0,
        unit="Medicare beneficiaries",
        kind=EstimateKind.MEASURED,
        formula="Σ emPOWER (test)",
    )
    return Estimate(
        label=f"{card.title} — affected panel",
        value=123.0,
        kind=EstimateKind.PLANNING_ESTIMATE,
        formula="national_count × share (test)",
        caveats=[PLANNING_CAVEAT],
        components=[measured],
    )


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    eng: Engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('clin') / 'web.db'}")
    init_db(eng)
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    facilities = attribute_facilities(raw, ZipCountyCrosswalk.load(), CountyIndex.load()).facilities
    upsert_facilities(eng, facilities)
    events = load_scenario("ian_2022")
    upsert_events(eng, events)
    result = match(
        events,
        load_cards(CARDS_DIR),
        facilities,
        load_profile(PROFILES_DIR / "va.yaml"),
        _panel,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    upsert_action_items(eng, result.items)
    return TestClient(create_app(eng))


def test_tel_links_wrap_digits_and_escape_text() -> None:
    html = str(tel_links("Call <KHARES: 866-446-3507; older KCER number: 1-866-901-3773>."))
    assert KHARES in html and KCER in html
    assert "&lt;KHARES" in html, "card text is escaped, not trusted as HTML"
    assert str(tel_links("no numbers here")) == "no numbers here"


def test_card_6_detail_renders_both_hotlines_and_contested_caveat(client: TestClient) -> None:
    html = client.get("/card-library/outage-dialysis").text
    assert KHARES in html and KCER in html
    assert "the survival signal is borderline" in html, "contested finding (§4) as a caveat"
    assert "[SHARED]" not in html


def test_card_2_detail_renders_contested_mechanism_caveat(client: TestClient) -> None:
    html = client.get("/card-library/heat-antipsychotics").text
    assert "The physiological mechanism is contested" in html


def test_patient_view_makes_hotlines_tappable(client: TestClient) -> None:
    html = client.get(
        "/demo/patient-view", params={**IAN, "facility": "vha_673", "card": "outage-dialysis"}
    ).text
    assert KHARES in html and KCER in html
    assert "[SHARED]" not in html


def test_provenance_popover_labels_planning_estimates(client: TestClient) -> None:
    html = client.get(
        "/dashboard/facilities/vha_673/cards", params={**IAN, "role": "care_team"}
    ).text
    planning = ESTIMATE_KIND_LABELS[EstimateKind.PLANNING_ESTIMATE]
    measured = ESTIMATE_KIND_LABELS[EstimateKind.MEASURED]
    assert planning in html and 'data-kind="planning_estimate"' in html
    assert measured in html and 'data-kind="measured"' in html
    assert ESTIMATE_KIND_LABELS[EstimateKind.MODELED_ESTIMATE] not in html


def test_every_card_page_is_free_of_library_markup(client: TestClient) -> None:
    for card in load_cards(CARDS_DIR):
        html = client.get(f"/card-library/{card.id}").text
        assert "[SHARED]" not in html, card.id
