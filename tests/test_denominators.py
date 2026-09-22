"""M3: catchments, reference tables, and sized panels with provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from xevents.api import create_app
from xevents.cards import CARDS_DIR, load_cards
from xevents.denominators import PanelEstimator, ReferenceTables
from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.geography.catchment import assign_catchments, assign_stations, haversine_km
from xevents.models import Estimate, Facility
from xevents.profiles import PROFILES_DIR, Profile, load_profile
from xevents.providers.va_facilities import from_geojson
from xevents.store import (
    catchment_map,
    init_db,
    make_engine,
    replace_catchments,
    replace_stations,
    station_map,
    upsert_facilities,
)

REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"
pytestmark = pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")


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
def tables(profile: Profile, counties: CountyIndex) -> ReferenceTables:
    return ReferenceTables.load(profile.catchment.projection_year, county_ids=counties.ids())


@pytest.fixture(scope="module")
def engine(
    tmp_path_factory: pytest.TempPathFactory,
    facilities: list[Facility],
    counties: CountyIndex,
    profile: Profile,
) -> Engine:
    eng = make_engine(f"sqlite:///{tmp_path_factory.mktemp('m3') / 'm3.db'}")
    init_db(eng)
    upsert_facilities(eng, facilities)
    anchors = profile.catchment.anchor_classifications
    replace_catchments(eng, assign_catchments(facilities, counties, anchors))
    replace_stations(eng, assign_stations(facilities, anchors))
    return eng


@pytest.fixture(scope="module")
def estimator(profile: Profile, tables: ReferenceTables, engine: Engine) -> PanelEstimator:
    return PanelEstimator(profile, tables, catchment_map(engine), station_map(engine))


def test_haversine() -> None:
    assert abs(haversine_km(-122.68, 45.5, -122.33, 47.6) - 235) < 5  # Portland → Seattle ≈ 235 km


def test_reference_tables(tables: ReferenceTables) -> None:
    assert len(tables.veterans) > 3_000
    assert tables.veterans["41051"] > 20_000  # Multnomah
    assert tables.places["41051"]["diabetes"] == 9.5
    assert 14_000_000 < tables.national_veterans < 19_000_000
    assert "72000" not in tables.veterans and tables.veterans["72127"] > 0  # PR allocated
    assert tables.veterans["66010"] == 10538  # Guam territory row → its single county
    assert tables.excluded == {"99000": 77176}
    rate = tables.national_places_rate("diabetes")
    assert rate is not None and 8 < rate < 16


def test_every_county_assigned_once_to_a_station(
    engine: Engine, counties: CountyIndex, facilities: list[Facility]
) -> None:
    cm = catchment_map(engine)
    all_counties = [c for lst in cm.values() for c in lst]
    assert len(all_counties) == len(set(all_counties)) == len(counties)
    by_id = {f.id: f for f in facilities}
    for fid in cm:
        cls = by_id[fid].classification or ""
        assert cls.startswith(("VA Medical Center", "Health Care Center")), fid
    multnomah_station = next(fid for fid, lst in cm.items() if "41051" in lst)
    assert "Portland" in (by_id[multnomah_station].health_care_system or "")
    stations = station_map(engine)
    assert stations["vha_648"] == ("vha_648", "self")
    assert len(stations) == len(facilities)
    anchor_ids = {
        f.id
        for f in facilities
        if (f.classification or "").startswith(("VA Medical", "Health Care"))
    }
    assert {sid for sid, _ in stations.values()} <= anchor_ids
    assert set(cm) <= anchor_ids


def test_no_double_counting_of_veterans(estimator: PanelEstimator, tables: ReferenceTables) -> None:
    total = sum(estimator.veterans(f).value for f in estimator.catchment)
    assert abs(total - tables.national_veterans) < 1


@pytest.mark.parametrize("facility_id", ["vha_648", "vha_516", "vha_663"])
def test_every_card_returns_a_sized_panel_with_provenance(
    estimator: PanelEstimator, facility_id: str
) -> None:
    for card in load_cards(CARDS_DIR):
        panel = estimator.card_panel(facility_id, card)
        assert panel.value > 0, (facility_id, card.id)
        assert "×" in panel.formula or "condition_panel" in panel.formula
        assert panel.sources and panel.caveats
        assert panel.components and panel.components[0].value > 0
        assert any(c.label == "Veterans in catchment" for c in _walk(panel))


def _walk(e: Estimate) -> list[Estimate]:
    out = [e]
    for c in e.components:
        out.extend(_walk(c))
    return out


def test_rate_count_and_places_paths(estimator: PanelEstimator, profile: Profile) -> None:
    vets = estimator.veterans("vha_648").value
    bipolar = estimator.condition_panel("vha_648", "bipolar")
    assert bipolar.value == pytest.approx(vets * 0.50 * 0.030)
    assert "rate[bipolar]" in bipolar.formula and "vha_users" in bipolar.formula
    assert bipolar.components[0].label == "vha_users in catchment"
    dialysis = estimator.condition_panel("vha_648", "dialysis")
    assert 0 < dialysis.value < 52_000
    assert "national_count[dialysis]" in dialysis.formula
    copd = estimator.condition_panel("vha_648", "copd")
    assert 0 < copd.value < vets
    assert "PLACES copd" in copd.formula
    assert any("general population" in c for c in copd.caveats)


def test_class_share_and_sub_panels(estimator: PanelEstimator) -> None:
    cards = {c.id: c for c in load_cards(CARDS_DIR)}
    hf = estimator.card_panel("vha_648", cards["heat-heart-failure"])
    condition = hf.components[0]
    assert hf.value == pytest.approx(condition.value * 0.62)
    assert "hfref_ace_arb_arni_share" in hf.formula
    delivery = estimator.card_panel("vha_648", cards["hurricane-delivery-interruption"])
    labels = [c.label for c in delivery.components]
    assert any("Clozapine" in lbl for lbl in labels)
    cloz = next(c for c in delivery.components if "Clozapine" in c.label)
    assert cloz.value == pytest.approx(delivery.components[0].value * 0.04)
    lithium = estimator.card_panel("vha_648", cards["heat-lithium"])
    assert any("upper bound" in c.lower() for c in lithium.caveats)


def test_clinic_inherits_station_panel(
    estimator: PanelEstimator, facilities: list[Facility]
) -> None:
    clinic_id = next(
        fid for fid, (sid, method) in estimator.stations.items() if method == "health_care_system"
    )
    est = estimator.veterans(clinic_id)
    station_id = str(est.inputs["station_id"])
    assert station_id != clinic_id
    assert est.value == estimator.veterans(station_id).value > 0
    assert any("parent station" in c for c in est.caveats)


def test_dialysis_allocation_sums_to_national_count(estimator: PanelEstimator) -> None:
    total = sum(estimator.condition_panel(f, "dialysis").value for f in estimator.catchment)
    assert total == pytest.approx(52_000, rel=1e-6)


def test_national_anchors_within_tolerance(estimator: PanelEstimator) -> None:
    assert estimator.check_national_anchors(load_cards(CARDS_DIR)) == []


def test_panels_endpoint(engine: Engine) -> None:
    client = TestClient(create_app(engine))
    r = client.get("/facilities/vha_648/panels", params={"card": "heat-heart-failure"})
    assert r.status_code == 200
    doc = r.json()
    assert doc["facility"]["id"] == "vha_648"
    assert doc["veterans"]["value"] > 0
    panel = doc["panels"]["heat-heart-failure"]
    assert panel["value"] > 0 and panel["formula"] and panel["inputs"]["share"] == 0.62
    assert client.get("/facilities/vha_648/panels").json()["panels"].keys() >= {
        "heat-lithium",
        "outage-dialysis",
    }
    assert client.get("/facilities/vha_648/panels", params={"card": "nope"}).status_code == 404


def test_profile_keys_resolve(profile: Profile) -> None:
    from xevents.profiles import check_cards_against_profile

    assert check_cards_against_profile(load_cards(CARDS_DIR), profile) == []
    assert (
        profile.panel_multipliers["heat-heart-failure"].denominator_key
        == "hfref_ace_arb_arni_share"
    )


# --------------------------------------------------------------------------- review fixes


def test_unsized_sub_panels_are_declared_not_borrowed(estimator: PanelEstimator) -> None:
    """Card 3's LAI and OUD sub-panels have no reviewed denominator; they used to render as
    the whole schizophrenia panel (an opioid-use-disorder cohort sized as schizophrenia)."""
    cards = {c.id: c for c in load_cards()}
    panel = estimator.card_panel("vha_648", cards["hurricane-delivery-interruption"])
    labels = [c.label for c in panel.components]
    assert not any("LAI antipsychotic" in lbl or "OUD patients" in lbl for lbl in labels)
    assert any("Clozapine" in lbl for lbl in labels), "the clozapine share is still sized"
    assert panel.caveats[0].startswith("Not sized — no reviewed denominator")
    assert "OUD patients on methadone" in panel.caveats[0]
    assert "LAI antipsychotic" in panel.caveats[0]
    assert panel.value == panel.components[0].value, "headline stays the condition panel"


def test_multi_condition_card_headline_is_the_largest_panel(estimator: PanelEstimator) -> None:
    """Card 7 selects CHD or HF or COPD or asthma: the headline is the largest single
    condition panel, labelled a lower bound, not whichever key is listed first."""
    cards = {c.id: c for c in load_cards()}
    p7 = estimator.card_panel("vha_648", cards["cold-cardio-respiratory"])
    subs = [c for c in p7.components[1:] if "sub-panel" in c.label]
    assert p7.value == max(c.value for c in [p7.components[0], *subs])
    assert p7.value > p7.components[0].value, "asthma outranks the CHD primary at Portland"
    assert p7.formula.startswith("max(condition_panel, sub-panels) = Asthma")
    assert p7.caveats[0].startswith("Lower bound")
    assert not any("stands in for the class" in c for c in p7.caveats), "no class on Card 7"
    p8 = estimator.card_panel("vha_648", cards["smoke-copd-asthma"])
    assert p8.value >= p8.components[0].value
    # a card with a medication class keeps the class wording
    p1 = estimator.card_panel("vha_648", cards["heat-lithium"])
    assert any("stands in for the medication/device class" in c for c in p1.caveats)
    # cards 1-6 headline values are unchanged by the rule (no standalone sub-panels)
    for cid in ("heat-lithium", "outage-dialysis", "outage-insulin"):
        p = estimator.card_panel("vha_648", cards[cid])
        assert (
            p.value == p.components[0].value * (1 if cid != "heat-heart-failure" else 0.62)
            or cid == "heat-heart-failure"
        )


def test_unknown_places_measure_fails_loudly(estimator: PanelEstimator, profile: Profile) -> None:
    from xevents.profiles import Denominator

    profile.denominators["bogus"] = Denominator(places_measure="nosuch", basis="x", source="y")
    try:
        with pytest.raises(ValueError, match="PLACES measure 'nosuch'"):
            estimator.condition_panel("vha_648", "bogus")
    finally:
        del profile.denominators["bogus"]


def test_missing_vetpop_year_fails_loudly(counties: CountyIndex) -> None:
    with pytest.raises(ValueError, match="veterans_2031"):
        ReferenceTables.load(2031, county_ids=counties.ids())


def test_profile_check_rejects_a_measured_proxy_as_headline(profile: Profile) -> None:
    from xevents.profiles import check_cards_against_profile

    card = next(c for c in load_cards() if c.id == "outage-dialysis")
    bad = card.model_copy(
        update={
            "population_selector": card.population_selector.model_copy(
                update={"denominator_key": "empower_dme"}
            )
        }
    )
    problems = check_cards_against_profile([bad], profile)
    assert any("emPOWER measure" in p for p in problems), problems
    share = card.model_copy(
        update={
            "population_selector": card.population_selector.model_copy(
                update={"denominator_key": "clozapine_share_of_schizophrenia"}
            )
        }
    )
    assert any("is a share" in p for p in check_cards_against_profile([share], profile))
    assert check_cards_against_profile(load_cards(), profile) == []
