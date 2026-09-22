"""Server-rendered pages (Jinja2 + htmx) over the same store the JSON API serves.

Routes: ``/`` dashboard (scenario switcher + live toggle, event board, map),
``/dashboard/facilities/{id}`` drill-down (fired cards, clinician checklists, role toggle,
acknowledge), ``/demo/patient-view`` read-only patient/caregiver rendering.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Engine

from xevents.carbon import CarbonTable, load_carbon
from xevents.cards import load_cards
from xevents.geography.catchment import is_anchor
from xevents.geography.counties import CountyIndex
from xevents.models import ActionItem, ActionItemStatus, Event, EventSource, Role
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.eagle_i import ATTRIBUTION as EAGLEI_ATTRIBUTION
from xevents.providers.eagle_i import (
    COVERAGE_CAVEAT,
    CUSTOMERS_CAVEAT,
    DENOMINATOR_SOURCE,
    OVERCOUNT_CAVEAT,
)
from xevents.providers.replay import list_scenarios
from xevents.sources import load_backlog, load_registry
from xevents.store import (
    TransitionError,
    feed_status,
    get_event,
    get_facility,
    latest_feed_runs,
    list_action_items,
    list_events,
    list_facilities,
    transition_action_item,
)
from xevents.timeparse import BadTimestamp, parse_at, to_input_value

router = APIRouter(include_in_schema=False)
WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def asset_version() -> str:
    """Newest mtime across the static assets, used to bust browser caches. A stale cached
    copy of a script (or of a 404 for one) otherwise leaves a page silently broken."""
    static = WEB_DIR / "static"
    try:
        newest = max(f.stat().st_mtime for f in static.rglob("*") if f.is_file())
    except ValueError:
        return "0"
    return str(int(newest))


ASSET_V = asset_version()

# Two audiences, not three: caregiver wording is the same guidance addressed to whoever is
# helping, so it is shown beside the patient text rather than behind a third tab.
DISPLAY_ROLES: list[tuple[str, str]] = [
    ("care_team", "care team"),
    ("patient", "patient & caregiver"),
]
_CARBON: CarbonTable | None = None


def carbon_table() -> CarbonTable:
    global _CARBON
    if _CARBON is None:
        _CARBON = load_carbon()
    return _CARBON


def carbon_for(number: int) -> list[dict[str, object]]:
    table = carbon_table()
    return [
        {**e.model_dump(mode="json"), "citations": table.citations(e)}
        for e in table.for_card_number(number)
    ]


SEVERITY_RANK = {"Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1, "Unknown": 0}
STALE_AFTER_HOURS = 6.0


def _engine(request: Request) -> Engine:
    eng: Engine = request.app.state.engine
    return eng


_COUNTY_NAMES: dict[str, str] | None = None


_AQI_NAME = re.compile(r"^AQI \d+ \((.+)\)$")
_AQI_FORECAST_NAME = re.compile(r"^AQI forecast .+ \((.+)\)$")


def event_group(name: str) -> str:
    """AirNow event names carry the reading ("AQI 220 (PM2.5)", "AQI forecast Unhealthy
    (OZONE)"); group them by pollutant for summaries. Same rule: ``XMap.eventGroup``."""
    if m := _AQI_FORECAST_NAME.match(name):
        return f"AirNow AQI forecast ({m.group(1)})"
    m = _AQI_NAME.match(name)
    return f"AirNow AQI ({m.group(1)})" if m else name


def county_names() -> dict[str, str]:
    """FIPS → 'Name, ST', loaded once."""
    global _COUNTY_NAMES
    if _COUNTY_NAMES is None:
        index = CountyIndex.load()
        _COUNTY_NAMES = {
            sh.county.geoid: f"{sh.county.name}, {sh.county.state}" for sh in index.shapes()
        }
    return _COUNTY_NAMES


def _parse_at(value: str | None) -> datetime | None:
    try:
        return parse_at(value)
    except BadTimestamp as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _context(request: Request, scenario: str | None, at: str | None) -> dict[str, Any]:
    """Shared header state: scenario list, chosen scenario (None = live), as-of time."""
    from xevents.api import scenario_summary  # local import avoids a circular import

    scenarios = [scenario_summary(name) for name in list_scenarios()]
    chosen = scenario if scenario not in (None, "", "live") else None
    if chosen is not None and chosen not in {s["id"] for s in scenarios}:
        raise HTTPException(status_code=404, detail=f"unknown scenario {chosen}")
    runs: list[dict[str, Any]] = []
    if chosen is None:
        as_of = _parse_at(at) or datetime.now(UTC)
        feeds = feed_status(_engine(request))
        for f in feeds:
            last = f["last_ingested_at"]
            age = (as_of - datetime.fromisoformat(last)).total_seconds() / 3600 if last else None
            f["age_hours"] = round(age, 1) if age is not None else None
            f["stale"] = age is None or age > STALE_AFTER_HOURS
        runs = latest_feed_runs(_engine(request))
        for r in runs:
            age = (as_of - datetime.fromisoformat(r["run_at"])).total_seconds() / 3600
            r["run_hhmm"] = datetime.fromisoformat(r["run_at"]).strftime("%m-%d %H:%MZ")
            r["stale"] = r["status"] == "ok" and age > STALE_AFTER_HOURS
    else:
        summary = next(s for s in scenarios if s["id"] == chosen)
        as_of = _parse_at(at) or datetime.fromisoformat(summary["peak_at"])
        feeds = []
    eaglei_caveats = [CUSTOMERS_CAVEAT, COVERAGE_CAVEAT]
    eaglei_run = next((r for r in runs if r["provider"] == "eagle_i"), None)
    if eaglei_run and eaglei_run["status"] == "ok" and eaglei_run["detail"]:
        eaglei_caveats.append(f"Live {eaglei_run['detail'].split(';')[0]}.")
    return {
        "request": request,
        "asset_v": ASSET_V,
        "scenarios": scenarios,
        "scenario": chosen,
        "mode": "replay" if chosen else "live",
        "as_of": as_of,
        "as_of_iso": as_of.isoformat(),
        "as_of_input": to_input_value(as_of),
        "feeds": feeds,
        "runs": runs,
        "any_stale": (
            any(r["stale"] or r["status"] == "failed" for r in runs)
            if runs
            else (any(f["stale"] for f in feeds) if feeds else chosen is None)
        ),
        "eaglei": {
            "attribution": EAGLEI_ATTRIBUTION,
            "caveats": eaglei_caveats,
            "denominator": DENOMINATOR_SOURCE,
            "overcount": OVERCOUNT_CAVEAT,
        },
    }


def _items_at(
    request: Request, scenario: str | None, as_of: datetime, **kw: Any
) -> list[ActionItem]:
    return list_action_items(
        _engine(request), scenario=scenario, active_at=as_of, live_only=scenario is None, **kw
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    scenario: str | None = Query(default=None),
    at: str | None = Query(default=None),
) -> HTMLResponse:
    ctx = _context(request, scenario, at)
    engine = _engine(request)
    items = _items_at(request, ctx["scenario"], ctx["as_of"])
    events = list_events(
        engine,
        scenario=ctx["scenario"],
        active_at=ctx["as_of"],
        live_only=ctx["scenario"] is None,
    )
    facilities = {f.id: f for f in list_facilities(engine)}
    board: dict[str, dict[str, Any]] = {}
    for it in items:
        row = board.setdefault(
            it.scope_id,
            {
                "facility": facilities.get(it.scope_id),
                "cards": {},
                "panel": 0.0,
                "rank_score": 0.0,
                "severity": 0,
                "acuity_rank": 99,
                "acuity_class": "",
                "events": set(),
            },
        )
        row["cards"].setdefault(it.card_id, it.card_title)
        row["panel"] = max(row["panel"], it.panel.value if it.panel else 0.0)
        row["rank_score"] = max(row["rank_score"], it.rank_score)
        row["severity"] = max(row["severity"], SEVERITY_RANK[it.event_severity.value])
        if it.acuity_rank < row["acuity_rank"]:
            row["acuity_rank"], row["acuity_class"] = it.acuity_rank, it.acuity_class
        row["events"].add(it.event_name)

    def board_key(r: dict[str, Any]) -> tuple[int, float, int, str]:
        f = r["facility"]
        cls = (f.classification or "") if f else ""
        station_first = 0 if cls.startswith(("VA Medical Center", "Health Care Center")) else 1
        return (
            r["acuity_rank"],
            -(r["severity"] * r["rank_score"]),
            station_first,
            f.name if f else "",
        )

    ranked = sorted(board.values(), key=board_key)
    event_counts: dict[str, int] = {}
    for e in events:
        group = event_group(e.event_name)
        event_counts[group] = event_counts.get(group, 0) + 1
    ctx.update(
        board=ranked,
        events=sorted(events, key=lambda e: (e.onset, e.event_key))[:25],
        events_total=len(events),
        has_outage=any(e.source is EventSource.EAGLE_I for e in events),
        item_count=len(items),
        event_count=len(events),
        event_counts=sorted(event_counts.items(), key=lambda kv: -kv[1]),
        open_queue=sum(
            1 for i in items if i.status is ActionItemStatus.ISSUED and i.acuity_rank <= 1
        ),
    )
    return templates.TemplateResponse(request, "dashboard.html", ctx)


def _display_role(role: str) -> Role:
    """The page offers care team and patient & caregiver; the data keeps all three."""
    return Role.CARE_TEAM if role == "care_team" else Role.PATIENT


def _facility_cards(
    request: Request,
    facility_id: str,
    scenario: str | None,
    as_of: datetime,
    role: Role,
    card: str | None = None,
) -> list[dict[str, Any]]:
    items = _items_at(request, scenario, as_of, facility_id=facility_id)
    if card:
        items = [i for i in items if i.card_id == card]
    by_card: dict[str, dict[str, Any]] = {}
    for it in items:
        entry = by_card.setdefault(
            it.card_id,
            {
                "card_id": it.card_id,
                "title": it.card_title,
                "roles": {},
                "acuity_rank": it.acuity_rank,
            },
        )
        # keep the strongest event's item per role
        cur = entry["roles"].get(it.role.value)
        if (
            cur is None
            or SEVERITY_RANK[it.event_severity.value] > SEVERITY_RANK[cur.event_severity.value]
        ):
            entry["roles"][it.role.value] = it
    cards = sorted(by_card.values(), key=lambda c: c["acuity_rank"])
    # The card definition carries both phases' actions: the block shows the phase that applies
    # now at full strength and the other one as reference, all verbatim from the YAML.
    defs = {d.id: d for d in load_cards()}
    for c in cards:
        d = defs.get(str(c["card_id"]))
        c["def"] = d
        c["item"] = c["roles"].get(role.value)
        c["caregiver"] = c["roles"].get(Role.CAREGIVER.value) if role is Role.PATIENT else None
        c["any"] = next(iter(c["roles"].values()))
        c["carbon"] = carbon_for(d.number if d else 0)
    return cards


@router.get("/dashboard/facilities/{facility_id}", response_class=HTMLResponse)
def facility_page(
    request: Request,
    facility_id: str,
    scenario: str | None = None,
    at: str | None = None,
    role: str = "care_team",
) -> HTMLResponse:
    ctx = _context(request, scenario, at)
    facility = get_facility(_engine(request), facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail=f"unknown facility {facility_id}")
    if role not in {r for r, _ in DISPLAY_ROLES}:
        raise HTTPException(status_code=422, detail=f"unknown role {role}")
    role_enum = _display_role(role)
    cards = _facility_cards(request, facility_id, ctx["scenario"], ctx["as_of"], role_enum)
    ctx.update(
        facility=facility,
        cards=cards,
        role=role,
        display_roles=DISPLAY_ROLES,
        carbon_disclaimer=carbon_table().ui_disclaimer,
    )
    return templates.TemplateResponse(request, "facility.html", ctx)


@router.get("/dashboard/facilities/{facility_id}/cards", response_class=HTMLResponse)
def facility_cards_partial(
    request: Request,
    facility_id: str,
    scenario: str | None = None,
    at: str | None = None,
    role: str = "care_team",
    card: str | None = None,
    embed: bool = False,
) -> HTMLResponse:
    """The card block alone. The facility page swaps it in with htmx; the playback card
    focus fetches it with ``card=`` and ``embed=1`` so both surfaces render one partial."""
    ctx = _context(request, scenario, at)
    facility = get_facility(_engine(request), facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail=f"unknown facility {facility_id}")
    try:
        role_enum = Role(role)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown role {role}") from None
    cards = _facility_cards(
        request, facility_id, ctx["scenario"], ctx["as_of"], role_enum, card=card
    )
    ctx.update(
        facility=facility,
        facility_id=facility_id,
        cards=cards,
        role=role_enum.value,
        display_roles=DISPLAY_ROLES,
        embed=embed,
        carbon_disclaimer=carbon_table().ui_disclaimer,
    )
    return templates.TemplateResponse(request, "cards_partial.html", ctx)


@router.post("/dashboard/action-items/{item_id:path}/status", response_class=HTMLResponse)
def dashboard_status(request: Request, item_id: str, status: str = Query(...)) -> HTMLResponse:
    try:
        item = transition_action_item(_engine(request), item_id, ActionItemStatus(status))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown action item") from exc
    except (TransitionError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request, "status_badge.html", {"request": request, "item": item}
    )


@router.get("/demo/patient-view", response_class=HTMLResponse)
def patient_view(
    request: Request,
    facility: str = Query(...),
    card: str | None = Query(default=None),
    scenario: str | None = None,
    at: str | None = None,
    role: str = "patient",
    view: str = Query(default="card", pattern="^(card|pair)$"),
) -> HTMLResponse:
    """The light patient card, print-ready. ``view=pair`` sets the care-team block beside it
    so a reviewer sees both renderings of the same action item at once."""
    ctx = _context(request, scenario, at)
    fac = get_facility(_engine(request), facility)
    if fac is None:
        raise HTTPException(status_code=404, detail=f"unknown facility {facility}")
    role_enum = Role.PATIENT
    cards = _facility_cards(request, facility, ctx["scenario"], ctx["as_of"], role_enum)
    if card:
        cards = [c for c in cards if c["card_id"] == card]
        if not cards and card not in {c.id for c in load_cards()}:
            raise HTTPException(status_code=404, detail=f"unknown card {card}")
    care_by_card: dict[str, dict[str, Any]] = {}
    if view == "pair":
        care = _facility_cards(
            request, facility, ctx["scenario"], ctx["as_of"], Role.CARE_TEAM, card=card
        )
        care_by_card = {str(c["card_id"]): c for c in care}
    ctx.update(
        facility=fac,
        cards=cards,
        role=role_enum.value,
        card=card,
        view=view,
        care_by_card=care_by_card,
        display_roles=DISPLAY_ROLES,
        carbon_disclaimer=carbon_table().ui_disclaimer,
    )
    return templates.TemplateResponse(request, "patient_view.html", ctx)


def _event_rows(events: list[Event], items: list[ActionItem]) -> list[dict[str, Any]]:
    by_event: dict[str, set[str]] = {}
    for it in items:
        by_event.setdefault(it.event_key, set()).add(it.scope_id)
    return [
        {
            "event": e,
            "facilities": len(by_event.get(e.event_key, ())),
            "counties": len(e.geography.county_fips),
        }
        for e in events
    ]


@router.get("/dashboard/events", response_class=HTMLResponse)
def events_page(
    request: Request,
    scenario: str | None = None,
    at: str | None = None,
    window: str = Query(default="active", pattern="^(active|all)$"),
) -> HTMLResponse:
    """Explorable event list: everything stored for the scenario, or only what is active."""
    ctx = _context(request, scenario, at)
    engine = _engine(request)
    active_at = ctx["as_of"] if window == "active" else None
    events = list_events(
        engine, scenario=ctx["scenario"], active_at=active_at, live_only=ctx["scenario"] is None
    )
    items = _items_at(request, ctx["scenario"], ctx["as_of"])
    rows = _event_rows(sorted(events, key=lambda e: (e.onset, e.event_key)), items)
    ctx.update(rows=rows, window=window, total=len(rows))
    return templates.TemplateResponse(request, "events.html", ctx)


@router.get("/dashboard/events/{event_key:path}", response_class=HTMLResponse)
def event_page(
    request: Request, event_key: str, scenario: str | None = None, at: str | None = None
) -> HTMLResponse:
    ctx = _context(request, scenario, at)
    engine = _engine(request)
    event = get_event(engine, event_key)
    if event is None:
        raise HTTPException(status_code=404, detail=f"unknown event {event_key}")
    items = list_action_items(engine, scenario=event.scenario, include_superseded=True)
    mine = [i for i in items if i.event_key == event_key]
    facilities = {f.id: f for f in list_facilities(engine)}
    by_facility: dict[str, dict[str, Any]] = {}
    for it in mine:
        row = by_facility.setdefault(
            it.scope_id,
            {"facility": facilities.get(it.scope_id), "cards": {}, "status": it.status.value},
        )
        row["cards"].setdefault(it.card_id, it.card_title)
    names = county_names()
    counties = [(f, names.get(f, f)) for f in event.geography.county_fips]
    ctx.update(
        event=event,
        counties=sorted(counties, key=lambda c: c[1]),
        facilities=sorted(
            by_facility.values(), key=lambda r: r["facility"].name if r["facility"] else ""
        ),
        item_count=len(mine),
        superseded=sum(1 for i in mine if i.status is ActionItemStatus.SUPERSEDED),
    )
    return templates.TemplateResponse(request, "event.html", ctx)


def _source_status(runs: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    """One status for a live source from its providers' latest runs: failed beats stale
    beats ok; a source whose providers never ran (or were skipped) says so."""
    if not runs:
        return {"state": "none", "label": "no live run yet", "runs": []}
    for r in runs:
        at = datetime.fromisoformat(r["run_at"])
        r["run_hhmm"] = at.strftime("%m-%d %H:%MZ")
        r["stale"] = r["status"] == "ok" and (as_of - at).total_seconds() / 3600 > STALE_AFTER_HOURS
    if any(r["status"] == "failed" for r in runs):
        state, label = "failed", "last run failed"
    elif all(r["status"] == "skipped" for r in runs):
        state, label = "off", "not configured"
    elif any(r["stale"] for r in runs):
        state, label = "stale", "stale"
    else:
        state = "ok"
        label = f"{sum(r['events'] for r in runs if r['status'] == 'ok')} live events"
    return {"state": state, "label": label, "runs": runs}


@router.get("/sources", response_class=HTMLResponse)
def sources_page(
    request: Request, scenario: str | None = None, at: str | None = None
) -> HTMLResponse:
    """Every data source: what it provides, what it drives, where it covers — the live
    coverage limits stated plainly (EAGLE-I: Georgia and Ohio only) — and its last live run."""
    ctx = _context(request, scenario, at)
    engine = _engine(request)
    registry = load_registry()
    runs_by_provider = {r["provider"]: r for r in latest_feed_runs(engine)}
    now = datetime.now(UTC)
    replays: dict[str, list[str]] = {}
    for s in ctx["scenarios"]:
        for src in s.get("sources", []):
            replays.setdefault(src, []).append(s["id"])
    facilities = list_facilities(engine)
    anchors = load_profile(PROFILES_DIR / "va.yaml").catchment.anchor_classifications
    facility_facts = {
        "total": len(facilities),
        "stations": sum(1 for f in facilities if is_anchor(f, anchors)),
        "visns": len({f.visn for f in facilities if f.visn}),
        "states": len({f.state for f in facilities if f.state}),
    }
    rows: list[dict[str, Any]] = []
    for src in registry.sources:
        runs = [dict(runs_by_provider[p]) for p in src.live.runs if p in runs_by_provider]
        rows.append(
            {
                "src": src,
                "status": _source_status(runs, now) if src.live.mode == "live" else None,
                "replays": replays.get(src.event_source or "", []),
            }
        )
    layers = [
        (
            "event",
            "Event layer",
            "What is happening, and where: the hazard feeds cards trigger on.",
        ),
        ("shared", "Shared reference", "Geography every source is joined through."),
        (
            "medical",
            "Medical layer",
            "Who is affected: facilities, veterans and the estimates behind every panel.",
        ),
    ]
    ctx.update(
        guide=registry.guide,
        layers=[
            (key, title, blurb, [r for r in rows if r["src"].layer == key])
            for key, title, blurb in layers
        ],
        backlog=load_backlog(),
        facility_facts=facility_facts,
        live_problems=[
            r for r in rows if r["status"] and r["status"]["state"] in ("failed", "stale", "off")
        ],
        partial=[r for r in rows if r["src"].live.coverage_level == "partial"],
    )
    return templates.TemplateResponse(request, "sources.html", ctx)


@router.get("/playback", response_class=HTMLResponse)
def playback(request: Request) -> HTMLResponse:
    """The time-scrubbed map view. Rendered through Jinja only so it picks up ``asset_v``."""
    return templates.TemplateResponse(
        request, "playback.html", {"request": request, "asset_v": ASSET_V}
    )
