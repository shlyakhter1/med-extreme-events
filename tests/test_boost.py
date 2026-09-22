"""M9: the engine co-occurrence boost (requirements v2 §4) and the cold/winter products.

Heat or cold items in a county with an observed outage that cleared a card's threshold and
debounce move up one acuity class and are stamped with the outage; the outage's own items
get the annotation only. No boost when the outage is below threshold or not sustained.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xevents.cards import CARDS_DIR, load_cards
from xevents.engine import match
from xevents.models import (
    ActionItemStatus,
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
from xevents.providers.iem_archive import VTEC_NAMES, IEMArchiveProvider
from xevents.providers.nws import NWS_EVENT_TYPES, normalize_nws_event

T0 = datetime(2021, 2, 15, 6, tzinfo=UTC)
HARRIS = "48201"
CUSTOMERS = {HARRIS: 1_800_000}


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile(PROFILES_DIR / "va.yaml")


@pytest.fixture(scope="module")
def cards() -> list[Card]:
    return load_cards(CARDS_DIR)


FACILITY = Facility(
    id="vha_580",
    name="Houston",
    facility_type="va_health_facility",
    lat=29.7,
    lon=-95.4,
    operating_status=OperatingStatusCode.NORMAL,
    county_fips=HARRIS,
    visn="16",
    classification="VA Medical Center (VAMC)",
)


def _panels(fid: str, card: Card) -> Estimate:
    return Estimate(label="p", value=100.0, formula="test", inputs={})


def _weather(name: str, event_type: EventType, *, hours: int = 72) -> Event:
    return Event(
        source=EventSource.NWS,
        source_id=name.lower().replace(" ", "-"),
        event_type=event_type,
        event_name=name,
        severity=CapSeverity.SEVERE,
        temporality=Temporality.IMMINENT,
        onset=T0,
        expires=T0 + timedelta(hours=hours),
        geography=EventGeography(county_fips=[HARRIS]),
    )


def _outage(polls: int, pct: float, *, start: datetime = T0) -> list[Event]:
    out = int(CUSTOMERS[HARRIS] * pct / 100)
    return polls_to_events(
        [OutagePoll(HARRIS, start + timedelta(hours=h), out, "Harris", "TX") for h in range(polls)],
        CUSTOMERS,
        threshold_pct=1,  # emit everything; the cards' own thresholds decide the boost
        poll_minutes=60,
    )


def _rank(profile: Profile, cls: str) -> int:
    return profile.acuity_rank(cls)


def test_profile_boost_config(profile: Profile) -> None:
    cfg = profile.co_occurrence_boost
    assert cfg is not None and cfg.steps == 1
    assert {(p.primary, p.compounding) for p in cfg.pairs} == {
        ("heat", "power_outage"),
        ("extreme_cold", "power_outage"),
    }
    assert profile.acuity_order[-2:] == ["cold_cardio_respiratory", "smoke_copd_asthma"]


def test_cold_plus_outage_boosts_card_7(cards: list[Card], profile: Profile) -> None:
    cold = _weather("Extreme Cold Warning", EventType.EXTREME_COLD)
    outage = _outage(2, 30.0, start=T0 + timedelta(hours=6))
    result = match([cold, *outage], cards, [FACILITY], profile, _panels, now=T0)
    card7 = [i for i in result.items if i.card_id == "cold-cardio-respiratory"]
    assert card7 and {i.role for i in card7} == {Role.CARE_TEAM, Role.PATIENT}
    base = _rank(profile, "cold_cardio_respiratory")
    for it in card7:
        assert it.acuity_rank == base - 1, "one profile step up"
        assert it.acuity_class == "cold_cardio_respiratory", "the class label is unchanged"
        assert it.compounding_events == [outage[1].event_key], "only the poll that cleared debounce"
    # symmetric annotation on the outage's own items; their acuity is not bumped
    outage_items = [i for i in result.items if i.event_type is EventType.POWER_OUTAGE]
    assert outage_items and all(i.compounding_events == [cold.event_key] for i in outage_items)
    assert all(i.acuity_rank == _rank(profile, i.acuity_class) for i in outage_items)
    # boosted cold items now sort ahead of un-boosted heart-failure-class items
    ranks = [i.acuity_rank for i in result.items]
    assert ranks == sorted(ranks)


def test_heat_plus_outage_boosts_heat_cards(cards: list[Card], profile: Profile) -> None:
    heat = _weather("Excessive Heat Warning", EventType.HEAT)
    outage = _outage(3, 12.0)
    result = match([heat, *outage], cards, [FACILITY], profile, _panels, now=T0)
    heat_items = [i for i in result.items if i.event_type is EventType.HEAT]
    assert {i.card_id for i in heat_items} == {
        "heat-lithium",
        "heat-antipsychotics",
        "heat-heart-failure",
    }
    for it in heat_items:
        assert it.acuity_rank == max(0, _rank(profile, it.acuity_class) - 1)
        assert it.compounding_events == [outage[1].event_key, outage[2].event_key]
    # the two-poll debounce means the first poll never qualifies
    assert outage[0].event_key not in {k for i in heat_items for k in i.compounding_events}


def test_no_boost_when_outage_is_below_threshold_or_unsustained(
    cards: list[Card], profile: Profile
) -> None:
    heat = _weather("Excessive Heat Warning", EventType.HEAT)
    below = _outage(3, 5.0)  # 5% never clears any card's 10%
    result = match([heat, *below], cards, [FACILITY], profile, _panels, now=T0)
    assert not any(i.event_type is EventType.POWER_OUTAGE for i in result.items)
    for it in result.items:
        assert it.compounding_events == [] and it.acuity_rank == _rank(profile, it.acuity_class)
    single = _outage(1, 40.0)  # one poll: threshold met, debounce not
    result = match([heat, *single], cards, [FACILITY], profile, _panels, now=T0)
    assert not any(i.event_type is EventType.POWER_OUTAGE for i in result.items)
    assert all(i.compounding_events == [] for i in result.items)
    # a qualifying outage that does not overlap the heat event's window is not compounding
    later = _outage(2, 40.0, start=T0 + timedelta(days=10))
    result = match([heat, *later], cards, [FACILITY], profile, _panels, now=T0)
    assert all(i.compounding_events == [] for i in result.items if i.event_type is EventType.HEAT)
    # hurricane items are not a boost pair: annotation-free even with an overlapping outage
    watch = _weather("Hurricane Watch", EventType.HURRICANE_FLOOD)
    result = match([watch, *_outage(2, 40.0)], cards, [FACILITY], profile, _panels, now=T0)
    for it in result.items:
        if it.event_key == watch.event_key and it.status is not ActionItemStatus.SUPERSEDED:
            assert it.compounding_events == []


def test_boost_is_deterministic_and_never_below_zero(cards: list[Card], profile: Profile) -> None:
    heat = _weather("Excessive Heat Warning", EventType.HEAT)
    outage = _outage(2, 50.0)
    a = match([heat, *outage], cards, [FACILITY], profile, _panels, now=T0).items
    b = match([*reversed(outage), heat], cards, [FACILITY], profile, _panels, now=T0).items
    assert [(i.id, i.acuity_rank, i.compounding_events) for i in a] == [
        (i.id, i.acuity_rank, i.compounding_events) for i in b
    ]
    assert min(i.acuity_rank for i in a) >= 0


# --------------------------------------------------------------------------- cold products


def test_cold_products_are_tracked_under_current_names() -> None:
    current = {
        "Extreme Cold Warning",
        "Extreme Cold Watch",
        "Cold Weather Advisory",
        "Winter Storm Warning",
        "Winter Storm Watch",
        "Ice Storm Warning",
        "Blizzard Warning",
    }
    assert all(NWS_EVENT_TYPES[n] is EventType.EXTREME_COLD for n in current)
    assert not any(n in NWS_EVENT_TYPES for n in ("Wind Chill Warning", "Wind Chill Watch"))
    assert normalize_nws_event(VTEC_NAMES["WC.W"]) == ("Extreme Cold Warning", "Wind Chill Warning")
    assert VTEC_NAMES["EC.W"] == "Extreme Cold Warning" and VTEC_NAMES["BZ.W"] == "Blizzard Warning"
    assert {"EC", "CW", "WS", "IS", "BZ", "WC"} <= set(IEMArchiveProvider.PHENOMENA.split(","))
    card7 = next(c for c in load_cards(CARDS_DIR) if c.number == 7)
    listed = {n for t in card7.event_triggers for n in t.conditions.nws_events}
    assert listed == current, "cards list current names only"


# --------------------------------------------------------------------------- display


def test_compounding_chip_renders(cards: list[Card], profile: Profile, tmp_path: Path) -> None:
    """The boosted item shows a compounding chip linking to the outage event (M10 polish)."""
    from fastapi.testclient import TestClient

    from xevents.api import create_app
    from xevents.store import (
        init_db,
        make_engine,
        upsert_action_items,
        upsert_events,
        upsert_facilities,
    )

    cold = _weather("Extreme Cold Warning", EventType.EXTREME_COLD)
    outage = _outage(2, 30.0, start=T0 + timedelta(hours=6))
    result = match([cold, *outage], cards, [FACILITY], profile, _panels, now=T0)
    eng = make_engine(f"sqlite:///{tmp_path / 'boost.db'}")
    init_db(eng)
    upsert_facilities(eng, [FACILITY])
    upsert_events(eng, [cold, *outage])
    upsert_action_items(eng, result.items)
    client = TestClient(create_app(eng))
    html = client.get(
        f"/dashboard/facilities/{FACILITY.id}", params={"at": (T0 + timedelta(hours=8)).isoformat()}
    ).text
    assert "compounding · acuity +1" in html
    assert outage[1].event_key in html, "the chip names the compounding outage"
    assert "imminent → pre-event" in html


def test_compounding_chip_shows_three_and_a_count(
    cards: list[Card], profile: Profile, tmp_path: Path
) -> None:
    """A long outage stamps many polls on the boosted item; the chip names three and counts
    the rest instead of listing every poll."""
    from fastapi.testclient import TestClient

    from xevents.api import create_app
    from xevents.store import (
        init_db,
        make_engine,
        upsert_action_items,
        upsert_events,
        upsert_facilities,
    )

    cold = _weather("Extreme Cold Warning", EventType.EXTREME_COLD)
    outage = _outage(8, 30.0, start=T0 + timedelta(hours=2))
    result = match([cold, *outage], cards, [FACILITY], profile, _panels, now=T0)
    boosted = next(i for i in result.items if i.card_id == "cold-cardio-respiratory")
    assert len(boosted.compounding_events) == 7, "polls 2-8 clear the debounce"
    eng = make_engine(f"sqlite:///{tmp_path / 'chip.db'}")
    init_db(eng)
    upsert_facilities(eng, [FACILITY])
    upsert_events(eng, [cold, *outage])
    upsert_action_items(eng, result.items)
    html = (
        TestClient(create_app(eng))
        .get(
            f"/dashboard/facilities/{FACILITY.id}",
            params={"at": (T0 + timedelta(hours=5)).isoformat()},
        )
        .text
    )
    # the chip says compounding; the provenance line names three events and counts the rest
    assert "compounding · acuity +1" in html
    lines = [c.split("</div>")[0] for c in html.split("compounding with ")[1:]]
    chip = next(c for c in lines if "eagle_i:" in c)
    assert chip.count("/dashboard/events/eagle_i:") == 3 and "and 4 more" in chip
