"""Golden scenario tests — the engine's determinism contract.

Replaying a scenario must produce exactly the recorded action-item set (event, card,
facility, role, status, superseded_by). Regenerate deliberately with
``UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`` after an intended engine or fixture
change, and review the diff.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from xevents.cards import CARDS_DIR, load_cards
from xevents.denominators import PanelEstimator, ReferenceTables
from xevents.engine import MatchResult, match
from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.geography.catchment import assign_catchments, assign_stations
from xevents.models import ActionItem, Card, Estimate, Role
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.replay import load_scenario
from xevents.providers.va_facilities import from_geojson

GOLDEN_DIR = Path(__file__).parent / "golden"
REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"
FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)
pytestmark = pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")


@pytest.fixture(scope="module")
def world() -> tuple[list[Card], list, PanelEstimator]:  # type: ignore[type-arg]
    profile = load_profile(PROFILES_DIR / "va.yaml")
    counties = CountyIndex.load()
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    facilities = attribute_facilities(raw, ZipCountyCrosswalk.load(), counties).facilities
    anchors = profile.catchment.anchor_classifications
    catchment: dict[str, list[str]] = {}
    for a in assign_catchments(facilities, counties, anchors):
        catchment.setdefault(a.facility_id, []).append(a.county_fips)
    stations = {
        a.facility_id: (a.station_id, a.method) for a in assign_stations(facilities, anchors)
    }
    tables = ReferenceTables.load(profile.catchment.projection_year, county_ids=counties.ids())
    estimator = PanelEstimator(profile, tables, catchment, stations)
    return load_cards(CARDS_DIR), facilities, estimator


def run_scenario(scenario: str, world: tuple[list[Card], list, PanelEstimator]) -> MatchResult:  # type: ignore[type-arg]
    cards, facilities, estimator = world
    profile = load_profile(PROFILES_DIR / "va.yaml")

    def panels(fid: str, card: Card) -> Estimate | None:
        return estimator.card_panel(fid, card)

    # Production scopes action items to the stations that own a panel (scripts/match.py);
    # the golden contract must exercise the same scoping.
    stations = [f for f in facilities if estimator.owns_panel(f.id)]
    return match(
        load_scenario(scenario),
        cards,
        stations,
        profile,
        panels,
        now=FIXED_NOW,
        exposures=estimator.empower_dme,
    )


def compact(items: list[ActionItem]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "event": it.event_key,
            "card": it.card_id,
            "facility": it.scope_id,
            "role": it.role.value,
            "status": it.status.value,
            "superseded_by": it.superseded_by,
            "panel": round(it.panel.value) if it.panel else None,
        }
        for it in items
    ]
    return sorted(
        rows, key=lambda r: (str(r["event"]), str(r["card"]), str(r["facility"]), str(r["role"]))
    )


def check_golden(scenario: str, result: MatchResult) -> None:
    path = GOLDEN_DIR / f"{scenario}.json"
    got = compact(result.items)
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(json.dumps(got, indent=0) + "\n", encoding="utf-8")
    assert path.exists(), f"missing golden file {path}; run with UPDATE_GOLDEN=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert len(got) == len(expected), f"{scenario}: {len(got)} items vs golden {len(expected)}"
    assert got == expected, f"{scenario}: action-item set differs from golden file"


def test_heat_dome_2021_golden(world: tuple[list[Card], list, PanelEstimator]) -> None:  # type: ignore[type-arg]
    result = run_scenario("heat_dome_2021", world)
    check_golden("heat_dome_2021", result)
    items = result.items
    assert {i.card_id for i in items} == {
        "heat-lithium",
        "heat-antipsychotics",
        "heat-heart-failure",
    }
    facilities = {i.scope_id for i in items}
    assert {"vha_648", "vha_663", "vha_663A4"} <= facilities  # Portland, Seattle, American Lake
    issued = [i for i in items if i.superseded_by is None]
    assert issued and all(i.status.value == "issued" for i in issued)
    portland = [i for i in issued if i.scope_id == "vha_648" and i.role is Role.PATIENT]
    assert {i.card_id for i in portland} == {
        "heat-lithium",
        "heat-antipsychotics",
        "heat-heart-failure",
    }
    assert all(i.panel and i.panel.value > 0 for i in items)
    # watches are superseded by the warnings that followed them
    assert any(i.event_name == "Excessive Heat Watch" and i.superseded_by for i in items)


def test_ian_2022_golden(world: tuple[list[Card], list, PanelEstimator]) -> None:  # type: ignore[type-arg]
    result = run_scenario("ian_2022", world)
    check_golden("ian_2022", result)
    items = result.items
    assert {i.card_id for i in items} == {
        "hurricane-delivery-interruption",
        "outage-insulin",
        "outage-dialysis",
    }
    assert all(i.scope_id.startswith("vha_") for i in items)
    assert items[0].card_id == "outage-dialysis", "dialysis ranks first by acuity"
    assert items[0].acuity_rank == 0
    assert {"vha_516", "vha_675"} & {i.scope_id for i in items}  # Bay Pines, Orlando
    assert all(i.panel and i.panel.value > 0 for i in items)


def test_no_facility_duplicates_another_facilitys_panel(
    world: tuple[list[Card], list, PanelEstimator],  # type: ignore[type-arg]
) -> None:
    """Estimated patients must be counted once. Before action items were scoped to the
    stations that own a catchment, 70 facilities reported only 14 distinct panels because
    59 clinics repeated their station's estimate, inflating the total several-fold."""
    result = run_scenario("heat_dome_2021", world)
    for card_id in {i.card_id for i in result.items}:
        panels = {
            i.scope_id: round(i.panel.value, 3)
            for i in result.items
            if i.card_id == card_id and i.panel
        }
        assert len(set(panels.values())) == len(panels), (
            f"{card_id}: {len(panels)} facilities share {len(set(panels.values()))} panel values"
        )


def test_card_needs_at_least_one_estimated_patient(
    world: tuple[list[Card], list, PanelEstimator],  # type: ignore[type-arg]
) -> None:
    profile = load_profile(PROFILES_DIR / "va.yaml")
    assert profile.min_panel_patients >= 1.0
    for scenario in ("heat_dome_2021", "ian_2022"):
        result = run_scenario(scenario, world)
        for item in result.items:
            assert item.panel is not None
            assert item.panel.value >= profile.min_panel_patients, item.id
        assert any(not t.matched and "min_panel_patients" in t.reason for t in result.log) or all(
            t.matched or "min_panel" not in t.reason for t in result.log
        )


def test_replay_is_idempotent(world: tuple[list[Card], list, PanelEstimator]) -> None:  # type: ignore[type-arg]
    a = compact(run_scenario("heat_dome_2021", world).items)
    b = compact(run_scenario("heat_dome_2021", world).items)
    assert a == b


def test_smoke_scenario_fires_no_v1_card(world: tuple[list[Card], list, PanelEstimator]) -> None:  # type: ignore[type-arg]
    result = run_scenario("smoke_nyc_2023", world)
    assert result.items == []
    assert result.log and not any(t.matched for t in result.log)
