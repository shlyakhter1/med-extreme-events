"""Pure matching engine: (events, cards, facilities, panels) → action items. No I/O.

Deterministic: same inputs, same items, in the same order. Every trigger evaluation is
returned in a log (event id, card id, matched or why not) for auditability.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from xevents.models import (
    Action,
    ActionItem,
    ActionItemStatus,
    CapSeverity,
    Card,
    Estimate,
    Event,
    EventSource,
    EventTrigger,
    EventType,
    Facility,
    HeatRiskLevel,
    Phase,
    Role,
    SmokeDensity,
    Temporality,
)
from xevents.profiles import Profile

PanelLookup = Callable[[str, Card], Estimate | None]
ExposureLookup = Callable[[str], Estimate | None]

# Cross-family supersede (requirements v2 §2): an *observed* event of the second type may
# supersede forecast/imminent items of the first type on the listed cards only. Same-family
# supersession needs no entry. Engine data, not card data.
SUPERSEDE_FAMILIES: dict[tuple[EventType, EventType], frozenset[str]] = {
    (EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE): frozenset(
        {"hurricane-delivery-interruption", "outage-insulin", "outage-dialysis"}
    ),
}

SEVERITY_RANK = {
    CapSeverity.EXTREME: 4,
    CapSeverity.SEVERE: 3,
    CapSeverity.MODERATE: 2,
    CapSeverity.MINOR: 1,
    CapSeverity.UNKNOWN: 0,
}
HEATRISK_RANK = {
    HeatRiskLevel.YELLOW: 1,
    HeatRiskLevel.ORANGE: 2,
    HeatRiskLevel.RED: 3,
    HeatRiskLevel.MAGENTA: 4,
}
SMOKE_RANK = {SmokeDensity.LIGHT: 1, SmokeDensity.MEDIUM: 2, SmokeDensity.HEAVY: 3}


@dataclass(frozen=True)
class TriggerEvaluation:
    event_key: str
    card_id: str
    matched: bool
    reason: str


@dataclass
class MatchResult:
    items: list[ActionItem]
    log: list[TriggerEvaluation] = field(default_factory=list)


def phase_for(temporality: Temporality) -> Phase:
    """Event-side phase selector: what is happening decides which actions apply."""
    return Phase.DURING_EVENT if temporality is Temporality.OBSERVED else Phase.PRE_EVENT


def actions_for(card: Card, role: Role, temporality: Temporality) -> list[Action]:
    """The card's actions for ``role`` in the phase the event implies, plus phase-agnostic ones."""
    phase = phase_for(temporality)
    actions: list[Action] = getattr(card.actions, role.value)
    return [a for a in actions if a.phase in (phase, Phase.ANY)]


def _thresholds_hold(trigger: EventTrigger, event: Event) -> tuple[bool, str]:
    """Metric thresholds only (the part of a trigger that ``sustained_polls_min`` debounces)."""
    c = trigger.conditions
    if c.heatrisk_min is not None:
        level = event.metrics.get("heatrisk")
        try:
            rank = HEATRISK_RANK[HeatRiskLevel(str(level))]
        except (ValueError, KeyError):
            return False, "no heatrisk metric"
        if rank < HEATRISK_RANK[c.heatrisk_min]:
            return False, f"heatrisk {level} < {c.heatrisk_min}"
    if c.aqi_min is not None:
        aqi = event.metrics.get("aqi")
        if not isinstance(aqi, int | float) or aqi < c.aqi_min:
            return False, f"aqi {aqi} < {c.aqi_min}"
    if c.smoke_density_min is not None:
        density = event.metrics.get("smoke_density")
        try:
            rank = SMOKE_RANK[SmokeDensity(str(density))]
        except (ValueError, KeyError):
            return False, "no smoke_density metric"
        if rank < SMOKE_RANK[c.smoke_density_min]:
            return False, f"smoke_density {density} < {c.smoke_density_min}"
    if c.outage_pct_min is not None:
        pct = event.metrics.get("outage_pct")
        if not isinstance(pct, int | float) or pct < c.outage_pct_min:
            return False, f"outage_pct {pct} < {c.outage_pct_min}"
    return True, "thresholds hold"


def trigger_matches(
    trigger: EventTrigger, event: Event, history: list[Event] | None = None
) -> tuple[bool, str]:
    """All set conditions of one trigger must hold.

    ``history`` is the chain of earlier contiguous events from the same source, type and
    geography (oldest first) — the previous provider polls. ``sustained_polls_min`` counts
    how many of the most recent polls, this one included, satisfy the metric thresholds.
    """
    if trigger.type != event.event_type:
        return False, f"type {event.event_type} != {trigger.type}"
    c = trigger.conditions
    if c.nws_events and (event.source != EventSource.NWS or event.event_name not in c.nws_events):
        return False, f"'{event.event_name}' not in nws_events"
    if c.temporality is not None and event.temporality is not c.temporality:
        return False, f"temporality {event.temporality} != {c.temporality}"
    ok, why = _thresholds_hold(trigger, event)
    if not ok:
        return False, why
    if c.fema_declared and event.source != EventSource.OPENFEMA:
        return False, "not a FEMA declaration"
    if c.sustained_polls_min is not None:
        streak = 1
        for prior in reversed(history or []):
            if not _thresholds_hold(trigger, prior)[0]:
                break
            streak += 1
        if streak < c.sustained_polls_min:
            return False, f"sustained {streak} poll(s) < {c.sustained_polls_min}"
    return True, "matched"


def card_matches(card: Card, event: Event, history: list[Event] | None = None) -> tuple[bool, str]:
    reasons = []
    for trigger in card.event_triggers:
        ok, why = trigger_matches(trigger, event, history)
        if ok:
            return True, why
        reasons.append(why)
    return False, "; ".join(reasons)


def _poll_key(event: Event) -> tuple[str, str, tuple[str, ...]]:
    return (event.source.value, event.event_type.value, tuple(event.geography.county_fips))


def poll_histories(events: list[Event]) -> dict[str, list[Event]]:
    """event_key → the contiguous chain of earlier events with the same source, type and
    geography (a provider's previous polls). A gap between one event's expiry and the next
    onset breaks the chain, so a debounce streak restarts after the condition lapses."""
    chains: dict[tuple[str, str, tuple[str, ...]], list[Event]] = {}
    out: dict[str, list[Event]] = {}
    for event in sorted(events, key=lambda e: (e.onset, e.event_key)):
        key = _poll_key(event)
        chain = chains.get(key, [])
        if chain and chain[-1].expires < event.onset:
            chain = []
        out[event.event_key] = list(chain)
        chains[key] = [*chain, event]
    return out


def rank_for(event: Event, panel: Estimate | None, exposure: Estimate | None) -> tuple[float, str]:
    """Ranking multiplier within an acuity class (requirements v2 §5): for outage events
    the measured percent out times the measured emPOWER count; otherwise the panel size."""
    pct = event.metrics.get("outage_pct")
    if (
        event.event_type is EventType.POWER_OUTAGE
        and exposure is not None
        and isinstance(pct, int | float)
    ):
        score = float(pct) * exposure.value
        return score, (
            f"outage_pct × empower_dme = {float(pct):g} × {exposure.value:.0f} = {score:.0f}"
        )
    value = panel.value if panel else 0.0
    return value, f"panel = {value:.0f}"


def item_window_start(event: Event, card: Card) -> datetime:
    """Forecast and imminent events open the card's pre-event lead window (act days ahead);
    an observed event is already happening, so its item starts at the observation. Without
    this, a replay showed an outage measured on Feb 18 as the current reading on Feb 16."""
    if event.temporality is Temporality.OBSERVED:
        return event.onset
    return event.onset - timedelta(days=card.window_days.max)


def item_window_end(event: Event) -> datetime:
    """An outage reading is current from its run up to, but not including, the next run.
    Poll events are contiguous (one expires when the next begins, which the debounce chain
    relies on), so the item ends one second earlier: at an hour boundary exactly one reading
    is current instead of two."""
    if event.event_type is EventType.POWER_OUTAGE and event.temporality is Temporality.OBSERVED:
        return max(event.onset, event.expires - timedelta(seconds=1))
    return event.expires


def _item_id(event_key: str, card_id: str, facility_id: str, role: Role) -> str:
    return f"{event_key}|{card_id}|{facility_id}|{role.value}"


def _build_item(
    event: Event,
    card: Card,
    facility: Facility,
    role: Role,
    actions: list[Action],
    profile: Profile,
    panel: Estimate | None,
    exposure: Estimate | None,
    now: datetime,
) -> ActionItem:
    rank_score, rank_formula = rank_for(event, panel, exposure)
    message = None
    if role in (Role.PATIENT, Role.CAREGIVER):
        message = " ".join(a.text for a in actions)
    safety = None
    if card.safety.do_not_stop_medication:
        safety = f"Don't stop your medication — {profile.escalation_default.rstrip('.').lower()}."
    escalation = [
        e
        if e.response is not None
        else e.model_copy(update={"response": profile.escalation_default})
        for e in card.escalation
    ]
    return ActionItem(
        id=_item_id(event.event_key, card.id, facility.id, role),
        event_key=event.event_key,
        event_type=event.event_type,
        event_name=event.event_name,
        event_severity=event.severity,
        event_temporality=event.temporality,
        phase=phase_for(event.temporality),
        card_id=card.id,
        card_version=card.version,
        card_title=card.title,
        scope_id=facility.id,
        role=role,
        actions=list(actions),
        message=message,
        escalation=escalation,
        safety_message=safety,
        evidence_tier=card.evidence_tier,
        sources=[s.citation for s in card.sources],
        panel=panel,
        exposure=exposure,
        rank_score=rank_score,
        rank_formula=rank_formula,
        acuity_class=card.acuity_class,
        acuity_rank=profile.acuity_rank(card.acuity_class),
        window_start=item_window_start(event, card),
        window_end=item_window_end(event),
        scenario=event.scenario,
        created_at=now,
    )


def match(
    events: list[Event],
    cards: list[Card],
    facilities: list[Facility],
    profile: Profile,
    panels: PanelLookup,
    *,
    now: datetime,
    exposures: ExposureLookup | None = None,
) -> MatchResult:
    """Produce one ActionItem per (event, card, facility, role), acuity-ranked, with
    weaker overlapping items of the same (card, facility, role, event type) marked
    superseded by the strongest. An item carries the actions of the phase its event
    implies (forecast/imminent → pre-event, observed → during-event) plus the phase-agnostic
    ones; a role with nothing to say in that phase gets no item.

    A card is only issued where its estimated panel reaches ``profile.min_panel_patients``:
    an aggregate estimate below one patient does not describe anybody to act on. Callers
    pass the facilities that own a panel (the stations), so the same estimated patients
    are not counted again at every clinic in the catchment.
    """
    by_county: dict[str, list[Facility]] = {}
    for f in facilities:
        if f.county_fips:
            by_county.setdefault(f.county_fips, []).append(f)
    log: list[TriggerEvaluation] = []
    items: list[ActionItem] = []
    by_key = {e.event_key: e for e in events}
    facility_county = {f.id: f.county_fips for f in facilities}
    panel_cache: dict[tuple[str, str], Estimate | None] = {}
    exposure_cache: dict[str, Estimate | None] = {}
    histories = poll_histories(events)
    for event in sorted(events, key=lambda e: (e.onset, e.event_key)):
        in_scope: dict[str, Facility] = {}
        for fips in event.geography.county_fips:
            for f in by_county.get(fips, []):
                in_scope[f.id] = f
        for card in cards:
            ok, why = card_matches(card, event, histories[event.event_key])
            log.append(TriggerEvaluation(event.event_key, card.id, ok, why))
            if not ok or not in_scope:
                continue
            role_actions = {role: actions_for(card, role, event.temporality) for role in Role}
            for fid in sorted(in_scope):
                facility = in_scope[fid]
                key = (fid, card.id)
                if key not in panel_cache:
                    panel_cache[key] = panels(fid, card)
                panel = panel_cache[key]
                if panel is not None and panel.value < profile.min_panel_patients:
                    reason = (
                        f"panel {panel.value:.2f} < min_panel_patients "
                        f"{profile.min_panel_patients} at {fid}"
                    )
                    log.append(TriggerEvaluation(event.event_key, card.id, False, reason))
                    continue
                exposure = None
                if exposures is not None and event.event_type is EventType.POWER_OUTAGE:
                    if fid not in exposure_cache:
                        exposure_cache[fid] = exposures(fid)
                    exposure = exposure_cache[fid]
                for role, actions in role_actions.items():
                    if not actions:
                        continue
                    items.append(
                        _build_item(
                            event, card, facility, role, actions, profile, panel, exposure, now
                        )
                    )
    _apply_supersession(items, by_key)
    _apply_co_occurrence_boost(items, by_key, facility_county, log, profile)
    items.sort(key=rank_key)
    return MatchResult(items=items, log=log)


def _apply_co_occurrence_boost(
    items: list[ActionItem],
    events: dict[str, Event],
    facility_county: dict[str, str | None],
    log: list[TriggerEvaluation],
    profile: Profile,
) -> None:
    """Requirements v2 §4: for each active item of a *primary* family (heat, cold) whose
    county also has a *compounding* event (an observed outage that cleared some card's
    threshold and debounce — i.e. matched in the log) overlapping its event window, raise
    the item ``steps`` profile classes in acuity and stamp ``compounding_events``. The
    compounding event's own items in that county get the annotation only. Pure and
    deterministic; no trigger grammar.
    """
    cfg = profile.co_occurrence_boost
    if cfg is None:
        return
    pairs = {(EventType(p.primary), EventType(p.compounding)) for p in cfg.pairs}
    primary_types = {p for p, _ in pairs}
    compounding_types = {c for _, c in pairs}
    qualifying = {t.event_key for t in log if t.matched}
    by_county: dict[str, list[Event]] = {}  # county → compounding events that cleared a card
    for e in events.values():
        if e.event_type in compounding_types and e.event_key in qualifying:
            for fips in e.geography.county_fips:
                by_county.setdefault(fips, []).append(e)

    def overlaps(a: Event, b: Event) -> bool:
        return a.onset <= b.expires and b.onset <= a.expires

    active = [it for it in items if it.status is not ActionItemStatus.SUPERSEDED]
    boosted: dict[tuple[str, EventType], set[str]] = {}  # (county, primary type) → event keys
    for it in active:
        county = facility_county.get(it.scope_id)
        if county is None or it.event_type not in primary_types:
            continue
        own = events[it.event_key]
        hits = sorted(
            e.event_key
            for e in by_county.get(county, [])
            if (it.event_type, e.event_type) in pairs and overlaps(own, e)
        )
        if not hits:
            continue
        it.compounding_events = hits
        it.acuity_rank = max(0, it.acuity_rank - cfg.steps)
        boosted.setdefault((county, it.event_type), set()).add(own.event_key)
    for it in active:  # symmetric annotation on the compounding events' own items
        county = facility_county.get(it.scope_id)
        if county is None or it.event_type not in compounding_types:
            continue
        own = events[it.event_key]
        hits = sorted(
            key
            for (c, primary), keys in boosted.items()
            if c == county and (primary, it.event_type) in pairs
            for key in keys
            if overlaps(own, events[key])
        )
        if hits:
            it.compounding_events = hits


def rank_key(item: ActionItem) -> tuple[int, int, float, str]:
    """The engine's item order: acuity class, CAP severity, rank score, then id. The store
    sorts with the same key so pages and the API agree with the engine."""
    return (
        item.acuity_rank,
        -SEVERITY_RANK[item.event_severity],
        -item.rank_score,
        item.id,
    )


def _family(item: ActionItem) -> EventType:
    """The event family an item competes in for supersession: its own type, or the type
    whose observed events may supersede it on this card (``SUPERSEDE_FAMILIES``)."""
    for (weaker, stronger), card_ids in SUPERSEDE_FAMILIES.items():
        if item.event_type is weaker and item.card_id in card_ids:
            return stronger
    return item.event_type


def _observed(item: ActionItem) -> bool:
    return item.event_temporality is Temporality.OBSERVED


def _supersedes(stronger: ActionItem, weaker: ActionItem) -> bool:
    """Observed beats forecast/imminent (never the reverse); within the same temporality
    class a higher CAP severity wins. Across event families only an observed event of the
    listed stronger type may supersede, and only forecast/imminent items. Measurements of
    the same outage (consecutive polls) never supersede each other: each is current during
    its own poll window, which the item window now equals (observed items have no lead)."""
    if stronger.event_type is not weaker.event_type:
        return _observed(stronger) and not _observed(weaker)
    if _observed(stronger) != _observed(weaker):
        return _observed(stronger)
    if stronger.event_type is EventType.POWER_OUTAGE and _observed(stronger):
        return False
    return SEVERITY_RANK[stronger.event_severity] > SEVERITY_RANK[weaker.event_severity]


def _apply_supersession(items: list[ActionItem], events: dict[str, Event]) -> None:
    """Within (card, facility, role, event family), the strongest overlapping item wins;
    the others are marked superseded_by it. Strength: observed over forecast/imminent, then
    CAP severity, then later onset. Never duplicates, never downgrades observed → forecast.

    Overlap is judged on item windows (which include the card's pre-event lead), with one
    guard: an event that ended before the weaker event began cannot supersede it. Without
    the guard a Severe warning from last week suppressed this week's separate Minor
    advisory for the same card and facility, because the advisory's lead window reached
    back into the warning. The guard is one-directional on purpose: a newer observed
    outage still supersedes the pre-event items of a hurricane watch that has already
    expired — that is the forecast → observed transition the requirements describe.
    """
    groups: dict[tuple[str, str, str, str], list[ActionItem]] = {}
    for it in items:
        groups.setdefault((it.card_id, it.scope_id, it.role.value, _family(it).value), []).append(
            it
        )
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(
            key=lambda it: (
                not _observed(it),
                -SEVERITY_RANK[it.event_severity],
                it.window_end,
                it.id,
            )
        )
        for i, weaker in enumerate(group):
            for stronger in group[:i]:
                overlaps = (
                    weaker.window_start <= stronger.window_end
                    and stronger.window_start <= weaker.window_end
                )
                ended_before = events[stronger.event_key].expires < events[weaker.event_key].onset
                if overlaps and not ended_before and _supersedes(stronger, weaker):
                    weaker.status = ActionItemStatus.SUPERSEDED
                    weaker.superseded_by = stronger.id
                    break
