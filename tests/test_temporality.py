"""M6: the temporality axis and trigger schema v2.

Every event carries ``temporality``; an unmapped provider fails loudly. The engine derives
the action phase from it, debounces metric triggers over consecutive polls, and lets
observed events supersede forecast/imminent items (same family, or the listed cross-family
pairs) — never the reverse.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from xevents.cards import CARDS_DIR, load_cards
from xevents.engine import (
    SUPERSEDE_FAMILIES,
    actions_for,
    card_matches,
    match,
    phase_for,
    poll_histories,
)
from xevents.models import (
    ActionItemStatus,
    CapCertainty,
    CapSeverity,
    Card,
    Estimate,
    Event,
    EventGeography,
    EventSource,
    EventType,
    Facility,
    OperatingStatusCode,
    Phase,
    Role,
    Temporality,
    TriggerConditions,
)
from xevents.profiles import PROFILES_DIR, Profile, load_profile
from xevents.providers.base import ProviderError
from xevents.providers.nws import nws_temporality
from xevents.providers.replay import load_scenario

NOW = datetime(2022, 9, 28, 12, tzinfo=UTC)
LEE = "12071"


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile(PROFILES_DIR / "va.yaml")


@pytest.fixture(scope="module")
def cards() -> list[Card]:
    return load_cards(CARDS_DIR)


@pytest.fixture(scope="module")
def by_id(cards: list[Card]) -> dict[str, Card]:
    return {c.id: c for c in cards}


FACILITY = Facility(
    id="vha_516",
    name="Bay Pines",
    facility_type="va_health_facility",
    lat=27.8,
    lon=-82.8,
    operating_status=OperatingStatusCode.NORMAL,
    county_fips=LEE,
    visn="8",
    classification="VA Medical Center (VAMC)",
)


def _panels(facility_id: str, card: Card) -> Estimate:
    return Estimate(label="p", value=100.0, formula="test", inputs={})


def _nws(
    name: str,
    *,
    source_id: str,
    severity: CapSeverity,
    temporality: Temporality,
    onset: datetime = NOW,
    hours: int = 48,
) -> Event:
    return Event(
        source=EventSource.NWS,
        source_id=source_id,
        event_type=EventType.HURRICANE_FLOOD,
        event_name=name,
        severity=severity,
        temporality=temporality,
        onset=onset,
        expires=onset + timedelta(hours=hours),
        geography=EventGeography(county_fips=[LEE]),
    )


def _outage(poll: int, pct: float, *, onset: datetime | None = None, county: str = LEE) -> Event:
    """One EAGLE-I style poll: hourly, county-keyed, observed."""
    start = onset or (NOW + timedelta(hours=poll))
    return Event(
        source=EventSource.EAGLE_I,
        source_id=f"{county}:{start:%Y-%m-%dT%H}",
        event_type=EventType.POWER_OUTAGE,
        event_name="County power outage",
        severity=CapSeverity.MINOR,
        certainty=CapCertainty.OBSERVED,
        temporality=Temporality.OBSERVED,
        onset=start,
        expires=start + timedelta(hours=1),
        geography=EventGeography(county_fips=[county]),
        metrics={"outage_pct": pct, "customers_out": 1000, "county_customers": 10000},
    )


# --------------------------------------------------------------------------- loud failure


def test_event_without_temporality_fails_validation() -> None:
    with pytest.raises(ValidationError, match="temporality"):
        Event(
            source=EventSource.REPLAY,
            source_id="x",
            event_type=EventType.HEAT,
            event_name="Heat Advisory",
            onset=NOW,
            expires=NOW,
            geography=EventGeography(county_fips=[LEE]),
        )  # type: ignore[call-arg]


def test_fixture_record_without_temporality_fails_loudly(tmp_path: Path) -> None:
    record = _outage(0, 20.0).model_copy(update={"scenario": "bad"}).model_dump(mode="json")
    del record["temporality"]
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "events.json").write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(ValidationError, match="temporality"):
        load_scenario("bad", tmp_path)


def test_nws_product_without_suffix_mapping_fails_loudly() -> None:
    assert nws_temporality("Hurricane Watch", CapCertainty.LIKELY)[0] is Temporality.FORECAST
    assert nws_temporality("Hurricane Warning", CapCertainty.LIKELY)[0] is Temporality.IMMINENT
    assert nws_temporality("Heat Advisory", CapCertainty.UNKNOWN)[0] is Temporality.IMMINENT
    assert nws_temporality("Hurricane Watch", CapCertainty.OBSERVED)[0] is Temporality.OBSERVED
    with pytest.raises(ProviderError, match="Special Weather Statement"):
        nws_temporality("Special Weather Statement", CapCertainty.LIKELY)


def test_trigger_conditions_v2_schema() -> None:
    with pytest.raises(ValidationError, match="outage_forecast"):
        TriggerConditions.model_validate({"outage_forecast": True})
    with pytest.raises(ValidationError, match="sustained_polls_min needs a metric threshold"):
        TriggerConditions(temporality=Temporality.OBSERVED, sustained_polls_min=2)
    with pytest.raises(ValidationError, match="at least one threshold"):
        TriggerConditions()
    assert TriggerConditions(temporality=Temporality.OBSERVED).temporality is Temporality.OBSERVED
    ok = TriggerConditions(outage_pct_min=10, sustained_polls_min=2)
    assert ok.has_metric_threshold


# --------------------------------------------------------------------------- phase


def test_phase_derivation(by_id: dict[str, Card]) -> None:
    assert phase_for(Temporality.FORECAST) is Phase.PRE_EVENT
    assert phase_for(Temporality.IMMINENT) is Phase.PRE_EVENT
    assert phase_for(Temporality.OBSERVED) is Phase.DURING_EVENT
    card = by_id["outage-insulin"]
    pre = actions_for(card, Role.CARE_TEAM, Temporality.FORECAST)
    during = actions_for(card, Role.CARE_TEAM, Temporality.OBSERVED)
    assert pre and all(a.phase in (Phase.PRE_EVENT, Phase.ANY) for a in pre)
    assert during and all(a.phase in (Phase.DURING_EVENT, Phase.ANY) for a in during)
    assert {a.text for a in pre}.isdisjoint({a.text for a in during})
    # patient sentences are phase-agnostic on every card: identical in both phases
    assert actions_for(card, Role.PATIENT, Temporality.FORECAST) == actions_for(
        card, Role.PATIENT, Temporality.OBSERVED
    )


def test_items_carry_phase_actions(cards: list[Card], profile: Profile) -> None:
    watch = _nws(
        "Hurricane Watch",
        source_id="w",
        severity=CapSeverity.MODERATE,
        temporality=Temporality.FORECAST,
    )
    items = match([watch], cards, [FACILITY], profile, _panels, now=NOW).items
    care = next(i for i in items if i.card_id == "outage-dialysis" and i.role is Role.CARE_TEAM)
    assert care.event_temporality is Temporality.FORECAST and care.phase is Phase.PRE_EVENT
    assert all(a.phase in (Phase.PRE_EVENT, Phase.ANY) for a in care.actions)
    outage = match(
        [_outage(0, 15.0), _outage(1, 15.0)], cards, [FACILITY], profile, _panels, now=NOW
    )
    care = next(
        i for i in outage.items if i.card_id == "outage-dialysis" and i.role is Role.CARE_TEAM
    )
    assert care.phase is Phase.DURING_EVENT
    assert all(a.phase in (Phase.DURING_EVENT, Phase.ANY) for a in care.actions)
    assert any(a.phase is Phase.DURING_EVENT for a in care.actions)


# --------------------------------------------------------------------------- streaks


def test_sustained_polls_debounce(cards: list[Card], profile: Profile) -> None:
    by_id = {c.id: c for c in cards}
    first, second = _outage(0, 15.0), _outage(1, 15.0)
    ok, why = card_matches(by_id["outage-insulin"], first, [])
    assert not ok and "sustained 1 poll(s) < 2" in why
    assert card_matches(by_id["outage-insulin"], second, [first]) == (True, "matched")
    assert card_matches(by_id["outage-dialysis"], second, [first])[0]
    # Card 3 needs 25%: 15% never fires it, however long it lasts
    assert not card_matches(by_id["hurricane-delivery-interruption"], second, [first])[0]
    big = [_outage(0, 30.0), _outage(1, 30.0)]
    assert card_matches(by_id["hurricane-delivery-interruption"], big[1], big[:1])[0]
    # a poll that drops below the threshold restarts the streak
    dip = [_outage(0, 15.0), _outage(1, 5.0), _outage(2, 15.0)]
    assert not card_matches(by_id["outage-insulin"], dip[2], dip[:2])[0]


def test_poll_histories_follow_contiguous_chains() -> None:
    a, b = _outage(0, 15.0), _outage(1, 15.0)
    gap = _outage(0, 15.0, onset=NOW + timedelta(hours=5))
    other_county = _outage(1, 15.0, county="12103")
    hist = poll_histories([gap, b, other_county, a])
    assert hist[a.event_key] == []
    assert hist[b.event_key] == [a]
    assert hist[gap.event_key] == [], "a gap in polls breaks the chain"
    assert hist[other_county.event_key] == [], "chains are per geography"


def test_match_applies_debounce_end_to_end(cards: list[Card], profile: Profile) -> None:
    lone = match([_outage(0, 15.0)], cards, [FACILITY], profile, _panels, now=NOW)
    assert lone.items == []
    assert any("sustained 1 poll(s) < 2" in t.reason for t in lone.log)
    two = match([_outage(0, 15.0), _outage(1, 15.0)], cards, [FACILITY], profile, _panels, now=NOW)
    assert {i.card_id for i in two.items} == {"outage-insulin", "outage-dialysis"}
    assert {i.event_key for i in two.items} == {_outage(1, 15.0).event_key}, (
        "only the poll that completes the streak issues items"
    )


# --------------------------------------------------------------------------- supersede


def test_observed_outage_supersedes_hurricane_watch_items(
    cards: list[Card], profile: Profile
) -> None:
    assert SUPERSEDE_FAMILIES[(EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE)] == {
        "hurricane-delivery-interruption",
        "outage-insulin",
        "outage-dialysis",
    }
    watch = _nws(
        "Hurricane Watch",
        source_id="w",
        severity=CapSeverity.MODERATE,
        temporality=Temporality.FORECAST,
    )
    polls = [_outage(0, 15.0), _outage(1, 15.0)]
    items = match([watch, *polls], cards, [FACILITY], profile, _panels, now=NOW).items
    watch_items = {i.card_id: i for i in items if i.event_key == "nws:w" and i.role is Role.PATIENT}
    outage_items = {
        i.card_id: i
        for i in items
        if i.event_type is EventType.POWER_OUTAGE and i.role is Role.PATIENT
    }
    for card_id in ("outage-insulin", "outage-dialysis"):
        assert watch_items[card_id].status is ActionItemStatus.SUPERSEDED
        assert watch_items[card_id].superseded_by == outage_items[card_id].id
        assert outage_items[card_id].status is ActionItemStatus.ISSUED
    # 15% is below Card 3's 25% threshold: its watch item stands
    assert watch_items["hurricane-delivery-interruption"].status is ActionItemStatus.ISSUED


def test_observed_is_never_downgraded_by_a_stronger_forecast(
    cards: list[Card], profile: Profile
) -> None:
    warning = _nws(
        "Hurricane Warning",
        source_id="v",
        severity=CapSeverity.EXTREME,
        temporality=Temporality.IMMINENT,
        onset=NOW + timedelta(hours=2),
    )
    polls = [_outage(0, 15.0), _outage(1, 15.0)]
    items = match([warning, *polls], cards, [FACILITY], profile, _panels, now=NOW).items
    outage = [i for i in items if i.event_type is EventType.POWER_OUTAGE]
    assert outage and all(i.status is ActionItemStatus.ISSUED for i in outage)
    warn = [
        i
        for i in items
        if i.event_key == "nws:v" and i.card_id != "hurricane-delivery-interruption"
    ]
    assert warn and all(i.status is ActionItemStatus.SUPERSEDED for i in warn), (
        "an Extreme-severity warning still yields to the measured outage"
    )


def test_same_family_observed_supersedes_forecast(cards: list[Card], profile: Profile) -> None:
    heat_county = Facility.model_validate({**FACILITY.model_dump(), "county_fips": "41051"})
    common = {
        "event_type": EventType.HEAT,
        "geography": EventGeography(county_fips=["41051"]),
        "onset": NOW,
        "expires": NOW + timedelta(hours=48),
    }
    watch = Event(
        source=EventSource.NWS,
        source_id="hw",
        event_name="Excessive Heat Watch",
        severity=CapSeverity.SEVERE,
        temporality=Temporality.FORECAST,
        **common,
    )
    observed = Event(
        source=EventSource.NWS,
        source_id="ha",
        event_name="Heat Advisory",
        severity=CapSeverity.MINOR,
        certainty=CapCertainty.OBSERVED,
        temporality=Temporality.OBSERVED,
        **common,
    )
    items = match([watch, observed], cards, [heat_county], profile, _panels, now=NOW).items
    assert all(
        i.status is ActionItemStatus.SUPERSEDED
        and i.superseded_by
        and i.superseded_by.startswith("nws:ha|")
        for i in items
        if i.event_key == "nws:hw"
    )
    assert all(i.status is ActionItemStatus.ISSUED for i in items if i.event_key == "nws:ha")
    # no cross-family supersede outside the listed pairs: heat items ignore outage events
    outage_items = match(
        [watch, _outage(0, 50.0, county="41051"), _outage(1, 50.0, county="41051")],
        cards,
        [heat_county],
        profile,
        _panels,
        now=NOW,
    ).items
    assert all(i.status is ActionItemStatus.ISSUED for i in outage_items if i.event_key == "nws:hw")


def test_past_event_does_not_supersede_a_later_separate_event(
    cards: list[Card], profile: Profile
) -> None:
    """Item windows include the card's pre-event lead, so a Severe warning that ended on
    June 3 used to supersede a separate Minor advisory starting June 8 (its 7-day lead
    reached back into the warning). An event that ended before the weaker one began must
    not supersede it; a newer event may still supersede an older overlapping-lead one."""
    heat_facility = Facility.model_validate({**FACILITY.model_dump(), "county_fips": "41051"})
    jun1 = datetime(2026, 6, 1, tzinfo=UTC)

    def heat(name: str, sid: str, sev: CapSeverity, start: datetime, days: int) -> Event:
        return Event(
            source=EventSource.NWS,
            source_id=sid,
            event_type=EventType.HEAT,
            event_name=name,
            severity=sev,
            temporality=Temporality.IMMINENT,
            onset=start,
            expires=start + timedelta(days=days),
            geography=EventGeography(county_fips=["41051"]),
        )

    past = heat("Excessive Heat Warning", "past", CapSeverity.SEVERE, jun1, 2)
    later = heat("Heat Advisory", "later", CapSeverity.MINOR, jun1 + timedelta(days=7), 1)
    items = match([past, later], cards, [heat_facility], profile, _panels, now=jun1).items
    assert all(i.status is ActionItemStatus.ISSUED for i in items), (
        "two separate weeks of weather are two separate sets of items"
    )
    # the reverse order — a stronger warning arriving after a weaker advisory that already
    # ended — still supersedes, because the warning is the newer picture
    early = heat("Heat Advisory", "early", CapSeverity.MINOR, jun1, 1)
    strong = heat(
        "Excessive Heat Warning", "strong", CapSeverity.SEVERE, jun1 + timedelta(days=3), 2
    )
    items = match([early, strong], cards, [heat_facility], profile, _panels, now=jun1).items
    assert all(i.status is ActionItemStatus.SUPERSEDED for i in items if i.event_key == "nws:early")
