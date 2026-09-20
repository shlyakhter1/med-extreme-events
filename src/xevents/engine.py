"""Pure matching engine: (events, cards, facilities, panels) → action items. No I/O.

Deterministic: same inputs, same items, in the same order. Every trigger evaluation is
returned in a log (event id, card id, matched or why not) for auditability.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from xevents.models import (
    ActionItem,
    ActionItemStatus,
    CapSeverity,
    Card,
    Estimate,
    Event,
    EventSource,
    EventTrigger,
    Facility,
    HeatRiskLevel,
    Role,
)
from xevents.profiles import Profile

PanelLookup = Callable[[str, Card], Estimate | None]

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


def trigger_matches(trigger: EventTrigger, event: Event) -> tuple[bool, str]:
    """All set conditions of one trigger must hold."""
    if trigger.type != event.event_type:
        return False, f"type {event.event_type} != {trigger.type}"
    c = trigger.conditions
    if c.nws_events and (event.source != EventSource.NWS or event.event_name not in c.nws_events):
        return False, f"'{event.event_name}' not in nws_events"
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
    if c.fema_declared and event.source != EventSource.OPENFEMA:
        return False, "not a FEMA declaration"
    if c.outage_forecast and not event.metrics.get("outage_forecast"):
        return False, "no outage forecast"
    return True, "matched"


def card_matches(card: Card, event: Event) -> tuple[bool, str]:
    reasons = []
    for trigger in card.event_triggers:
        ok, why = trigger_matches(trigger, event)
        if ok:
            return True, why
        reasons.append(why)
    return False, "; ".join(reasons)


def _item_id(event_key: str, card_id: str, facility_id: str, role: Role) -> str:
    return f"{event_key}|{card_id}|{facility_id}|{role.value}"


def _build_item(
    event: Event,
    card: Card,
    facility: Facility,
    role: Role,
    profile: Profile,
    panel: Estimate | None,
    now: datetime,
) -> ActionItem:
    actions = getattr(card.actions, role.value)
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
        acuity_class=card.acuity_class,
        acuity_rank=profile.acuity_rank(card.acuity_class),
        window_start=event.onset - timedelta(days=card.window_days.max),
        window_end=event.expires,
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
) -> MatchResult:
    """Produce one ActionItem per (event, card, facility, role), acuity-ranked, with
    weaker overlapping items of the same (card, facility, role, event type) marked
    superseded by the strongest."""
    by_county: dict[str, list[Facility]] = {}
    for f in facilities:
        if f.county_fips:
            by_county.setdefault(f.county_fips, []).append(f)
    log: list[TriggerEvaluation] = []
    items: list[ActionItem] = []
    panel_cache: dict[tuple[str, str], Estimate | None] = {}
    for event in sorted(events, key=lambda e: (e.onset, e.event_key)):
        in_scope: dict[str, Facility] = {}
        for fips in event.geography.county_fips:
            for f in by_county.get(fips, []):
                in_scope[f.id] = f
        for card in cards:
            ok, why = card_matches(card, event)
            log.append(TriggerEvaluation(event.event_key, card.id, ok, why))
            if not ok or not in_scope:
                continue
            for fid in sorted(in_scope):
                facility = in_scope[fid]
                key = (fid, card.id)
                if key not in panel_cache:
                    panel_cache[key] = panels(fid, card)
                panel = panel_cache[key]
                for role in Role:
                    if role is Role.CAREGIVER and not card.actions.caregiver:
                        continue
                    items.append(_build_item(event, card, facility, role, profile, panel, now))
    _apply_supersession(items)
    items.sort(key=_rank_key)
    return MatchResult(items=items, log=log)


def _rank_key(item: ActionItem) -> tuple[int, int, float, str]:
    return (
        item.acuity_rank,
        -SEVERITY_RANK[item.event_severity],
        -(item.panel.value if item.panel else 0.0),
        item.id,
    )


def _apply_supersession(items: list[ActionItem]) -> None:
    """Within (card, facility, role, event_type), the strongest overlapping item wins;
    the others are marked superseded_by it. Strength: CAP severity, then later onset."""
    groups: dict[tuple[str, str, str, str], list[ActionItem]] = {}
    for it in items:
        groups.setdefault((it.card_id, it.scope_id, it.role.value, it.event_type.value), []).append(
            it
        )
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda it: (-SEVERITY_RANK[it.event_severity], it.window_end, it.id))
        for i, weaker in enumerate(group):
            for stronger in group[:i]:
                overlaps = (
                    weaker.window_start <= stronger.window_end
                    and stronger.window_start <= weaker.window_end
                )
                if (
                    overlaps
                    and SEVERITY_RANK[stronger.event_severity]
                    > SEVERITY_RANK[weaker.event_severity]
                ):
                    weaker.status = ActionItemStatus.SUPERSEDED
                    weaker.superseded_by = stronger.id
                    break
