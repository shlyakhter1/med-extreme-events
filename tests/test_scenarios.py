"""Replay scenarios: the three fixtures load, land in the store, carry expected geography."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from xevents.models import EventSource, EventType
from xevents.providers.replay import ReplayProvider, list_scenarios, load_scenario
from xevents.store import delete_scenario_events, init_db, list_events, make_engine, upsert_events


def test_five_scenarios_exist() -> None:
    assert list_scenarios() == [
        "heat_dome_2021",
        "ian_2022",
        "smoke_canada_2026",
        "smoke_nyc_2023",
        "uri_2021",
    ]


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
    assert {e.event_type for e in events} == {EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE}
    assert all(e.geography.county_fips for e in events)
    outages = [e for e in events if e.source is EventSource.EAGLE_I]
    assert outages and all(e.temporality.value == "observed" for e in outages)
    assert all(len(e.geography.county_fips) == 1 and e.geography.states == ["FL"] for e in outages)
    assert all(10 <= float(e.metrics["outage_pct"]) <= 100 for e in outages)
    lee = [e for e in outages if e.geography.county_fips == ["12071"]]
    assert lee and max(float(e.metrics["outage_pct"]) for e in lee) >= 25, (
        "Lee County lost most customers"
    )
    assert all(e.expires - e.onset == timedelta(hours=1) for e in outages), "hourly maxima"


def test_uri_2021_geography() -> None:
    events = load_scenario("uri_2021")
    cold = [e for e in events if e.source is EventSource.NWS]
    assert cold and all(e.event_type is EventType.EXTREME_COLD for e in cold)
    assert all(e.geography.states == ["TX"] for e in cold)
    names = {e.event_name for e in cold}
    assert {"Extreme Cold Warning", "Winter Storm Warning"} <= names
    assert not any("Wind Chill" in n for n in names), "legacy names are normalized"
    legacy = [e for e in cold if "raw_nws_event" in e.metrics]
    assert legacy and {str(e.metrics["raw_nws_event"]) for e in legacy} <= {
        "Wind Chill Warning",
        "Wind Chill Watch",
        "Wind Chill Advisory",
    }
    outages = [e for e in events if e.source is EventSource.EAGLE_I]
    assert len(outages) > 10_000, "the largest outage in the EAGLE-I record"
    assert any(e.geography.county_fips == ["48201"] for e in outages)  # Harris
    flagged = [e for e in outages if "outage_pct_raw" in e.metrics]
    assert flagged and all(float(e.metrics["outage_pct"]) == 100 for e in flagged)


def test_smoke_canada_2026_geography() -> None:
    events = load_scenario("smoke_canada_2026")
    by_source = {s: [e for e in events if e.source is s] for s in EventSource}
    assert len(by_source[EventSource.HMS]) == 21  # 7 days × 3 densities
    aqi = by_source[EventSource.AIRNOW]
    assert aqi and all(e.event_type is EventType.AIR_POLLUTION for e in aqi)
    assert all(e.temporality.value == "observed" and float(e.metrics["aqi"]) >= 101 for e in aqi)
    assert all(e.expires - e.onset == timedelta(hours=24) for e in aqi), "daily archive rows"
    assert {s for e in aqi for s in e.geography.states} >= {"MI", "WI", "NY", "MD"}
    heat = by_source[EventSource.NWS]
    assert heat and all(e.event_type is EventType.HEAT for e in heat)


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
