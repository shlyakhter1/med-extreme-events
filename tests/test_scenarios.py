"""Replay scenarios: the three fixtures load, land in the store, carry expected geography."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from xevents.models import EventSource, EventType
from xevents.providers.replay import ReplayProvider, list_scenarios, load_scenario
from xevents.store import delete_scenario_events, init_db, list_events, make_engine, upsert_events


def test_three_scenarios_exist() -> None:
    assert list_scenarios() == ["heat_dome_2021", "ian_2022", "smoke_nyc_2023"]


def test_heat_dome_2021_geography() -> None:
    events = load_scenario("heat_dome_2021")
    assert all(e.scenario == "heat_dome_2021" and e.source is EventSource.NWS for e in events)
    warnings = [e for e in events if e.event_name == "Excessive Heat Warning"]
    assert warnings
    covered = {c for e in warnings for c in e.geography.county_fips}
    assert {"41051", "53033", "41005", "53053"} <= covered  # Multnomah, King, Clackamas, Pierce
    assert all(e.geography.county_fips for e in events), "every archived alert resolves to counties"
    assert (
        min(e.onset for e in events)
        < datetime(2021, 6, 27, tzinfo=UTC)
        < max(e.expires for e in events)
    )


def test_ian_2022_geography() -> None:
    events = load_scenario("ian_2022")
    names = {e.event_name for e in events}
    assert {
        "Hurricane Warning",
        "Hurricane Watch",
        "Tropical Storm Warning",
        "Storm Surge Warning",
    } <= names
    hurricane = [e for e in events if e.event_name == "Hurricane Warning"]
    assert any("12071" in e.geography.county_fips for e in hurricane)  # Lee County (landfall)
    fema = [e for e in events if e.source is EventSource.OPENFEMA]
    assert len(fema) == 1 and len(fema[0].geography.county_fips) == 67
    assert all(e.event_type is EventType.HURRICANE_FLOOD for e in events)
    assert all(e.geography.county_fips for e in events)


def test_smoke_nyc_2023_geography() -> None:
    events = load_scenario("smoke_nyc_2023")
    assert len(events) == 9 and all(e.source is EventSource.HMS for e in events)
    assert {e.metrics["smoke_density"] for e in events} == {"Light", "Medium", "Heavy"}
    heavy_jun7 = next(e for e in events if e.source_id == "2023-06-07:heavy")
    assert "36061" in heavy_jun7.geography.county_fips
    assert all(e.event_type is EventType.WILDFIRE_SMOKE for e in events)


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = make_engine(f"sqlite:///{tmp_path / 'events.db'}")
    init_db(eng)
    return eng


def test_replay_provider_and_store_round_trip(engine: Engine) -> None:
    provider = ReplayProvider("ian_2022")
    events = provider.fetch(provider.window())
    assert len(events) == len(load_scenario("ian_2022"))
    assert upsert_events(engine, events) == len(events)
    assert upsert_events(engine, events) == len(events), "upsert by natural key is idempotent"
    stored = list_events(engine, scenario="ian_2022")
    assert len(stored) == len(events)
    assert {e.event_key for e in stored} == {e.event_key for e in events}
    lee = list_events(engine, scenario="ian_2022", county_fips="12071")
    assert lee and all("12071" in e.geography.county_fips for e in lee)
    landfall = datetime(2022, 9, 28, 18, tzinfo=UTC)
    active = list_events(
        engine, scenario="ian_2022", active_at=landfall, event_type="hurricane_flood"
    )
    assert any(e.event_name == "Hurricane Warning" for e in active)
    round_trip = next(e for e in stored if e.source_id == "4673")
    assert (
        round_trip.geography.county_fips
        == next(e for e in events if e.source_id == "4673").geography.county_fips
    )
    assert delete_scenario_events(engine, "ian_2022") == len(events)
    assert list_events(engine, scenario="ian_2022") == []
