"""M8: emPOWER measured exposure layer — reference build, catchment rollup, the Card 6
sub-panel, dual-denominator display and the outage ranking rule (outage_pct × emPOWER)."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from xevents.api import create_app
from xevents.cards import CARDS_DIR, load_cards
from xevents.denominators import (
    EMPOWER_UNIT,
    MEDICARE_PROXY_CAVEAT,
    PanelEstimator,
    ReferenceTables,
    load_empower,
)
from xevents.engine import match, rank_for
from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.geography.catchment import assign_catchments, assign_stations
from xevents.models import (
    CapSeverity,
    Card,
    Estimate,
    Event,
    EventGeography,
    EventSource,
    EventType,
    Facility,
    OperatingStatusCode,
    Role,
    Temporality,
)
from xevents.profiles import PROFILES_DIR, Profile, load_profile
from xevents.providers.eagle_i import OutagePoll, polls_to_events
from xevents.providers.va_facilities import from_geojson
from xevents.store import (
    catchment_map,
    init_db,
    list_action_items,
    make_engine,
    replace_catchments,
    replace_stations,
    station_map,
    upsert_action_items,
    upsert_events,
    upsert_facilities,
)

REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"
SAMPLES = Path(__file__).parent / "fixtures" / "reference"
pytestmark = pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")
T0 = datetime(2022, 9, 28, 18, tzinfo=UTC)


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile(PROFILES_DIR / "va.yaml")


@pytest.fixture(scope="module")
def counties() -> CountyIndex:
    return CountyIndex.load()


@pytest.fixture(scope="module")
def facilities(counties: CountyIndex) -> list[Facility]:
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    return attribute_facilities(raw, ZipCountyCrosswalk.load(), counties).facilities


@pytest.fixture(scope="module")
def engine(
    tmp_path_factory: pytest.TempPathFactory,
    facilities: list[Facility],
    counties: CountyIndex,
    profile: Profile,
) -> Engine:
    eng = make_engine(f"sqlite:///{tmp_path_factory.mktemp('m8') / 'm8.db'}")
    init_db(eng)
    upsert_facilities(eng, facilities)
    anchors = profile.catchment.anchor_classifications
    replace_catchments(eng, assign_catchments(facilities, counties, anchors))
    replace_stations(eng, assign_stations(facilities, anchors))
    return eng


@pytest.fixture(scope="module")
def estimator(profile: Profile, counties: CountyIndex, engine: Engine) -> PanelEstimator:
    tables = ReferenceTables.load(profile.catchment.projection_year, county_ids=counties.ids())
    return PanelEstimator(profile, tables, catchment_map(engine), station_map(engine))


# --------------------------------------------------------------------------- reference


def test_build_script_parses_service_rows() -> None:
    spec = importlib.util.spec_from_file_location(
        "build_empower", Path(__file__).parents[1] / "scripts" / "build_empower.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    county = json.loads((SAMPLES / "empower_county_sample.json").read_text(encoding="utf-8"))
    rows = {r["county_fips"]: r for r in mod.rows_from(county["features"], mod.COUNTY_KEYS)}
    assert rows["12071"]["power_dependent_dme"] == 7418 and rows["12071"]["state"] == "FL"
    assert rows["48201"]["medicare_benes"] > rows["48201"]["power_dependent_dme"] > 0
    zips = json.loads((SAMPLES / "empower_zip_sample.json").read_text(encoding="utf-8"))
    zrows = mod.rows_from(zips["features"], mod.ZIP_KEYS)
    assert all(r["county_fips"] == "12071" and len(r["zip"]) == 5 for r in zrows)
    assert any(r["power_dependent_dme"] == 11 for r in zrows), "masked small cells read 11"


def test_reference_file_has_vintage_header_and_loads() -> None:
    rows, header = load_empower()
    assert "vintage" in header and "retrieved" in header, header
    assert len(rows) > 3200 and all(len(k) == 5 for k in rows)
    assert rows["12071"]["power_dependent_dme"] == 7418
    assert "medicare_benes" in rows["12071"]


# --------------------------------------------------------------------------- estimator


def test_empower_dme_rolls_up_catchment_counties(estimator: PanelEstimator) -> None:
    e = estimator.empower_dme("vha_516")  # Bay Pines
    assert e.unit == EMPOWER_UNIT and e.value > 0
    assert "emPOWER, measured" in e.label
    assert e.caveats[0] == MEDICARE_PROXY_CAVEAT
    assert any("masks small cells" in c for c in e.caveats)
    assert any("vintage" in s for s in e.sources)
    counties = estimator.catchment["vha_516"]
    expected = sum(
        estimator.tables.empower[c]["power_dependent_dme"] or 0
        for c in counties
        if c in estimator.tables.empower
    )
    assert e.value == expected
    assert e.inputs["counties"] == len(counties)


def test_card_6_sub_panel_is_measured_not_a_share(estimator: PanelEstimator) -> None:
    cards = {c.id: c for c in load_cards(CARDS_DIR)}
    card = cards["outage-dialysis"]
    assert card.version == "1.2.0"
    sub = next(
        s for s in card.population_selector.sub_panels if s.key == "electricity_dependent_dme"
    )
    assert sub.denominator_key == "empower_dme"
    assert {d.system.value for d in sub.device_classes} == {"empower"}
    panel = estimator.card_panel("vha_516", card)
    assert panel.unit == "veterans", "the veteran estimate stays the panel"
    comp = next(c for c in panel.components if "Electricity-dependent DME at home" in c.label)
    assert comp.unit == EMPOWER_UNIT and comp.value > 0
    assert comp.value == estimator.empower_dme("vha_516").value
    assert MEDICARE_PROXY_CAVEAT in comp.caveats
    dialysis = panel.components[0]
    assert dialysis.unit == "veterans" and comp.value != dialysis.value


def test_addendum_strings_landed_on_card_6() -> None:
    card = next(c for c in load_cards(CARDS_DIR) if c.number == 6)
    assert any(
        a.text.startswith("If your medical equipment needs electricity")
        for a in card.actions.patient
    )
    assert any(
        a.text.startswith("Confirm backup power") and a.phase.value == "pre_event"
        for a in card.actions.care_team
    )
    assert any("less than 4 hours" in e.signs for e in card.escalation)
    assert any(
        e.signs == "Oxygen interruption with breathlessness" and e.emergency
        for e in card.escalation
    )


# --------------------------------------------------------------------------- ranking


def _facility(fid: str, county: str) -> Facility:
    return Facility(
        id=fid,
        name=fid,
        facility_type="va_health_facility",
        lat=27.0,
        lon=-82.0,
        operating_status=OperatingStatusCode.NORMAL,
        county_fips=county,
        visn="8",
        classification="VA Medical Center (VAMC)",
    )


def test_rank_for_uses_measured_times_measured() -> None:
    outage = Event(
        source=EventSource.EAGLE_I,
        source_id="x",
        event_type=EventType.POWER_OUTAGE,
        event_name="Power outage (EAGLE-I)",
        temporality=Temporality.OBSERVED,
        onset=T0,
        expires=T0 + timedelta(hours=1),
        geography=EventGeography(county_fips=["12071"]),
        metrics={"outage_pct": 15.0},
    )
    panel = Estimate(label="p", value=500.0, formula="f", inputs={})
    exposure = Estimate(label="e", value=3000.0, unit=EMPOWER_UNIT, formula="f", inputs={})
    score, formula = rank_for(outage, panel, exposure)
    assert score == 45_000.0 and formula == "outage_pct × empower_dme = 15 × 3000 = 45000"
    assert rank_for(outage, panel, None) == (500.0, "panel = 500")
    heat = outage.model_copy(update={"event_type": EventType.HEAT, "metrics": {}})
    assert rank_for(heat, panel, exposure) == (500.0, "panel = 500"), "non-outage: panel"


def test_outage_ranking_prefers_measured_exposure_over_panel_size(profile: Profile) -> None:
    """Two stations, same acuity class and severity: A has the larger veteran estimate,
    B the larger outage_pct × emPOWER product. B must rank first on outage items and A
    first on hurricane items."""
    cards = load_cards(CARDS_DIR)
    a, b = _facility("vha_A", "12071"), _facility("vha_B", "12103")
    customers = {"12071": 600_000, "12103": 360_000}
    polls = [
        OutagePoll("12071", T0, 60_000),  # 10 %
        OutagePoll("12071", T0 + timedelta(hours=1), 60_000),
        OutagePoll("12103", T0, 108_000),  # 30 %
        OutagePoll("12103", T0 + timedelta(hours=1), 108_000),
    ]
    events = polls_to_events(polls, customers, threshold_pct=10, poll_minutes=60)
    watch = Event(
        source=EventSource.NWS,
        source_id="w",
        event_type=EventType.HURRICANE_FLOOD,
        event_name="Hurricane Watch",
        severity=CapSeverity.MODERATE,
        temporality=Temporality.FORECAST,
        onset=T0 - timedelta(days=1),
        expires=T0 - timedelta(hours=2),
        geography=EventGeography(county_fips=["12071", "12103"]),
    )
    panels = {"vha_A": 900.0, "vha_B": 300.0}
    exposures = {"vha_A": 1_000.0, "vha_B": 2_000.0}

    def panel_of(fid: str, card: Card) -> Estimate:
        return Estimate(label="p", value=panels[fid], formula="test", inputs={})

    def exposure_of(fid: str) -> Estimate:
        return Estimate(
            label="e", value=exposures[fid], unit=EMPOWER_UNIT, formula="test", inputs={}
        )

    result = match(
        [watch, *events], cards, [a, b], profile, panel_of, now=T0, exposures=exposure_of
    )
    outage = [
        i
        for i in result.items
        if i.event_type is EventType.POWER_OUTAGE
        and i.card_id == "outage-dialysis"
        and i.role is Role.CARE_TEAM
    ]
    assert [i.scope_id for i in outage] == ["vha_B", "vha_A"]
    assert outage[0].rank_score == 30.0 * 2_000 and outage[1].rank_score == 10.0 * 1_000
    assert outage[0].rank_formula.startswith("outage_pct × empower_dme = 30 × 2000")
    assert outage[0].exposure is not None and outage[0].exposure.unit == EMPOWER_UNIT
    hurricane = [
        i
        for i in result.items
        if i.event_key == "nws:w" and i.card_id == "outage-dialysis" and i.role is Role.CARE_TEAM
    ]
    assert [i.scope_id for i in hurricane] == ["vha_A", "vha_B"], (
        "panel size still ranks weather items"
    )
    assert all(i.exposure is None and i.rank_formula.startswith("panel") for i in hurricane)


# --------------------------------------------------------------------------- display


def test_outage_item_shows_both_denominators_with_provenance(
    engine: Engine, estimator: PanelEstimator, profile: Profile, facilities: list[Facility]
) -> None:
    cards = load_cards(CARDS_DIR)
    lee = [f for f in facilities if f.county_fips == "12071" and estimator.owns_panel(f.id)]
    assert lee, "a panel-owning station sits in Lee County FL"
    polls = [
        OutagePoll("12071", T0, 90_000, "Lee", "FL"),
        OutagePoll("12071", T0 + timedelta(hours=1), 90_000, "Lee", "FL"),
    ]
    events = polls_to_events(polls, {"12071": 600_000}, threshold_pct=10, poll_minutes=60)
    upsert_events(engine, events)
    result = match(
        events, cards, lee, profile, estimator.card_panel, now=T0, exposures=estimator.empower_dme
    )
    assert result.items
    upsert_action_items(engine, result.items)
    fid = lee[0].id
    stored = list_action_items(engine, facility_id=fid, card_id="outage-dialysis")
    assert stored and stored[0].exposure is not None and stored[0].rank_score > 0
    assert stored[0].panel is not None and stored[0].panel.unit == "veterans"
    client = TestClient(create_app(engine))
    at = (T0 + timedelta(hours=1, minutes=30)).isoformat()
    html = client.get(f"/dashboard/facilities/{fid}", params={"at": at}).text
    assert "Affected panel ≈" in html, "veteran estimate line"
    assert (
        "electricity-dependent Medicare beneficiaries in catchment "
        "(emPOWER, measured; Medicare proxy — not veteran-specific)"
    ) in html
    assert "outage_pct × empower_dme = 15 ×" in html, "ranking formula in the popover"
    assert (
        "Electricity-dependent DME at home (sub-panel)" in html
        and "Medicare beneficiaries:" in html
    )
    assert MEDICARE_PROXY_CAVEAT in html
    rows = client.get("/action-items", params={"facility": fid, "compact": "1"}).json()
    row = next(r for r in rows["items"] if r["card_id"] == "outage-dialysis")
    assert row["exposure"] and row["rank_score"] > 0
