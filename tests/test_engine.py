"""Matching engine: pure, deterministic, with supersession; store status machine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from xevents.cards import CARDS_DIR, load_cards
from xevents.engine import card_matches, match
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
from xevents.store import (
    TransitionError,
    expire_action_items,
    get_action_item,
    init_db,
    list_action_items,
    make_engine,
    transition_action_item,
    upsert_action_items,
)

NOW = datetime(2021, 6, 24, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile(PROFILES_DIR / "va.yaml")


@pytest.fixture(scope="module")
def cards() -> list[Card]:
    return load_cards(CARDS_DIR)


def _facility(fid: str, county: str) -> Facility:
    return Facility(
        id=fid,
        name=fid,
        facility_type="va_health_facility",
        lat=45.5,
        lon=-122.6,
        operating_status=OperatingStatusCode.NORMAL,
        county_fips=county,
        visn="20",
        classification="VA Medical Center (VAMC)",
    )


def _event(
    name: str,
    counties: list[str],
    *,
    severity: CapSeverity,
    source_id: str,
    onset: datetime,
    hours: int = 48,
    event_type: EventType = EventType.HEAT,
    source: EventSource = EventSource.NWS,
    temporality: Temporality = Temporality.IMMINENT,
) -> Event:
    return Event(
        source=source,
        source_id=source_id,
        event_type=event_type,
        event_name=name,
        severity=severity,
        temporality=temporality,
        onset=onset,
        expires=onset + timedelta(hours=hours),
        geography=EventGeography(county_fips=counties),
        scenario=None,
    )


def _panels(facility_id: str, card: Card) -> Estimate:
    return Estimate(label="p", value=100.0 if card.number != 6 else 10.0, formula="test", inputs={})


FACILITIES = [
    _facility("vha_648", "41051"),
    _facility("vha_663", "53033"),
    _facility("vha_516", "12103"),
]


def test_trigger_matching(cards: list[Card]) -> None:
    by_id = {c.id: c for c in cards}
    heat = _event("Heat Advisory", ["41051"], severity=CapSeverity.MINOR, source_id="a", onset=NOW)
    assert card_matches(by_id["heat-lithium"], heat) == (True, "matched")
    assert card_matches(by_id["outage-dialysis"], heat)[0] is False
    watch = _event(
        "Hurricane Watch",
        ["12103"],
        severity=CapSeverity.MODERATE,
        source_id="b",
        onset=NOW,
        event_type=EventType.HURRICANE_FLOOD,
    )
    assert card_matches(by_id["outage-dialysis"], watch)[0]
    assert card_matches(by_id["heat-lithium"], watch)[0] is False
    fema = _event(
        "FEMA DR declaration: Hurricane",
        ["12103"],
        severity=CapSeverity.SEVERE,
        source_id="4673",
        onset=NOW,
        event_type=EventType.HURRICANE_FLOOD,
        source=EventSource.OPENFEMA,
    )
    assert card_matches(by_id["outage-dialysis"], fema)[0] is False, (
        "declarations are context, not triggers"
    )
    smoke = _event(
        "HMS smoke (Heavy)",
        ["41051"],
        severity=CapSeverity.SEVERE,
        source_id="s",
        onset=NOW,
        event_type=EventType.WILDFIRE_SMOKE,
        source=EventSource.HMS,
    )
    assert not any(card_matches(c, smoke)[0] for c in cards), "no v1 card fires on smoke"


def test_match_produces_items_per_facility_card_role(cards: list[Card], profile: Profile) -> None:
    heat = _event(
        "Excessive Heat Warning",
        ["41051", "53033"],
        severity=CapSeverity.SEVERE,
        source_id="ehw",
        onset=NOW,
    )
    result = match([heat], cards, FACILITIES, profile, _panels, now=NOW)
    items = result.items
    # 2 facilities in scope × 3 heat cards (1, 2, 4) × 2 roles (caregiver content is empty)
    assert len(items) == 2 * 3 * 2
    assert {i.scope_id for i in items} == {"vha_648", "vha_663"}
    assert {i.card_id for i in items} == {
        "heat-lithium",
        "heat-antipsychotics",
        "heat-heart-failure",
    }
    assert {i.role for i in items} == {Role.CARE_TEAM, Role.PATIENT}
    assert all(i.status is ActionItemStatus.ISSUED for i in items)
    assert [i.acuity_rank for i in items] == sorted(i.acuity_rank for i in items), "acuity-ranked"
    patient = next(i for i in items if i.role is Role.PATIENT and i.card_id == "heat-lithium")
    assert patient.message and patient.message.startswith("Heat can push your lithium")
    assert patient.safety_message and "Don't stop your medication" in patient.safety_message
    assert all(e.response for e in patient.escalation), "templated escalation fills nulls"
    assert (
        patient.window_start == heat.onset - timedelta(days=7)
        and patient.window_end == heat.expires
    )
    assert patient.panel is not None and patient.panel.value == 100.0
    assert patient.id == "nws:ehw|heat-lithium|vha_648|patient"
    assert len(result.log) == len(cards)
    assert sum(t.matched for t in result.log) == 3


def test_match_is_deterministic(cards: list[Card], profile: Profile) -> None:
    ev = [
        _event("Heat Advisory", ["41051"], severity=CapSeverity.MINOR, source_id="x", onset=NOW),
        _event(
            "Excessive Heat Warning",
            ["53033"],
            severity=CapSeverity.SEVERE,
            source_id="y",
            onset=NOW,
        ),
    ]
    a = match(ev, cards, FACILITIES, profile, _panels, now=NOW).items
    b = match(
        list(reversed(ev)), cards, list(reversed(FACILITIES)), profile, _panels, now=NOW
    ).items
    assert [i.id for i in a] == [i.id for i in b]


def test_strengthened_alert_supersedes(cards: list[Card], profile: Profile) -> None:
    watch = _event(
        "Excessive Heat Watch",
        ["41051"],
        severity=CapSeverity.MODERATE,
        source_id="w",
        onset=NOW,
        hours=72,
    )
    warning = _event(
        "Excessive Heat Warning",
        ["41051"],
        severity=CapSeverity.SEVERE,
        source_id="v",
        onset=NOW + timedelta(hours=12),
        hours=48,
    )
    items = match([watch, warning], cards, FACILITIES[:1], profile, _panels, now=NOW).items
    weak = [i for i in items if i.event_key == "nws:w"]
    strong = [i for i in items if i.event_key == "nws:v"]
    assert weak and strong
    assert all(i.status is ActionItemStatus.SUPERSEDED for i in weak)
    assert all(i.superseded_by and i.superseded_by.startswith("nws:v|") for i in weak)
    assert all(i.status is ActionItemStatus.ISSUED for i in strong)
    # same strength, no supersession
    twin = match(
        [watch, watch.model_copy(update={"source_id": "w2"})],
        cards,
        FACILITIES[:1],
        profile,
        _panels,
        now=NOW,
    ).items
    assert all(i.status is ActionItemStatus.ISSUED for i in twin)


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = make_engine(f"sqlite:///{tmp_path / 'items.db'}")
    init_db(eng)
    return eng


def test_store_upsert_idempotent_and_keeps_progress(
    engine: Engine, cards: list[Card], profile: Profile
) -> None:
    heat = _event("Heat Advisory", ["41051"], severity=CapSeverity.MINOR, source_id="h", onset=NOW)
    items = match([heat], cards, FACILITIES[:1], profile, _panels, now=NOW).items
    assert upsert_action_items(engine, items) == {
        "inserted": len(items),
        "updated": 0,
        "unchanged": 0,
    }
    assert upsert_action_items(engine, items) == {
        "inserted": 0,
        "updated": 0,
        "unchanged": len(items),
    }
    first = items[0].id
    transition_action_item(engine, first, ActionItemStatus.DELIVERED)
    acked = transition_action_item(engine, first, ActionItemStatus.ACKNOWLEDGED)
    assert acked.status is ActionItemStatus.ACKNOWLEDGED and acked.acknowledged_at is not None
    with pytest.raises(TransitionError):
        transition_action_item(engine, first, ActionItemStatus.ISSUED)
    with pytest.raises(KeyError):
        transition_action_item(engine, "nope", ActionItemStatus.DELIVERED)
    # re-run with a longer window: content updates, acknowledgement survives
    longer = heat.model_copy(update={"expires": heat.expires + timedelta(days=1)})
    items2 = match([longer], cards, FACILITIES[:1], profile, _panels, now=NOW + timedelta(hours=1))
    counts = upsert_action_items(engine, items2.items)
    assert counts["updated"] == len(items) and counts["inserted"] == 0
    stored = get_action_item(engine, first)
    assert stored is not None
    assert stored.status is ActionItemStatus.ACKNOWLEDGED
    assert stored.window_end == longer.expires
    assert stored.created_at == NOW, "created_at is preserved across re-runs"
    # supersession applied on re-run; lifted when the stronger alert disappears
    warning = _event(
        "Excessive Heat Warning", ["41051"], severity=CapSeverity.SEVERE, source_id="w", onset=NOW
    )
    both = match([longer, warning], cards, FACILITIES[:1], profile, _panels, now=NOW).items
    upsert_action_items(engine, both)
    assert get_action_item(engine, first).status is ActionItemStatus.SUPERSEDED  # type: ignore[union-attr]
    assert (
        list_action_items(engine, facility_id="vha_648", role="patient", card_id="heat-lithium")[
            0
        ].event_key
        == "nws:w"
    )
    upsert_action_items(
        engine, match([longer], cards, FACILITIES[:1], profile, _panels, now=NOW).items
    )
    assert get_action_item(engine, first).status is ActionItemStatus.ISSUED  # type: ignore[union-attr]
    # expiry
    assert expire_action_items(engine, NOW + timedelta(days=30)) > 0
    assert all(
        i.status is ActionItemStatus.EXPIRED for i in list_action_items(engine, status="expired")
    )


def test_list_filters_active_at(engine: Engine, cards: list[Card], profile: Profile) -> None:
    heat = _event(
        "Heat Advisory", ["41051"], severity=CapSeverity.MINOR, source_id="h", onset=NOW, hours=24
    )
    upsert_action_items(
        engine, match([heat], cards, FACILITIES[:1], profile, _panels, now=NOW).items
    )
    assert list_action_items(engine, active_at=NOW + timedelta(hours=1))
    assert list_action_items(engine, active_at=NOW - timedelta(days=8)) == []
    assert list_action_items(engine, active_at=NOW + timedelta(days=2)) == []
