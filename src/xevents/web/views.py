"""Server-rendered pages (Jinja2 + htmx) over the same store the JSON API serves.

Routes: ``/`` dashboard (scenario switcher + live toggle, event board, map),
``/dashboard/facilities/{id}`` drill-down (fired cards, clinician checklists, role toggle,
acknowledge), ``/demo/patient-view`` read-only patient/caregiver rendering.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Engine

from xevents.carbon import CarbonTable, load_carbon
from xevents.cards import load_cards
from xevents.engine import safety_message
from xevents.geography.catchment import is_anchor
from xevents.geography.counties import CountyIndex
from xevents.models import ActionItem, ActionItemStatus, Event, Role
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.eagle_i import ATTRIBUTION as EAGLEI_ATTRIBUTION
from xevents.providers.eagle_i import (
    COVERAGE_CAVEAT,
    CUSTOMERS_CAVEAT,
    DENOMINATOR_SOURCE,
    OVERCOUNT_CAVEAT,
)
from xevents.providers.replay import list_scenarios
from xevents.scenario_guide import load_guide
from xevents.sources import load_backlog, load_registry
from xevents.store import (
    TransitionError,
    action_item_facts,
    compact_events,
    feed_status,
    get_event,
    get_facility,
    latest_feed_runs,
    list_action_items,
    list_events,
    list_facilities,
    replay_version,
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
        "show_asof": True,
        "show_banner": True,
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


def _anchor_classifications() -> list[str]:
    return list(load_profile(PROFILES_DIR / "va.yaml").catchment.anchor_classifications)


@router.get("/", response_class=HTMLResponse)
def monitor(request: Request) -> HTMLResponse:
    """Monitor: the one live-first map view (live now, the last two weeks, and the replays).
    Scenario, time and selection come from the query string and are read by playback.js.
    Rendered through Jinja only for ``asset_v`` and the station classes used in ranking."""
    return templates.TemplateResponse(
        request,
        "playback.html",
        {"request": request, "asset_v": ASSET_V, "anchors": _anchor_classifications()},
    )


def _monitor_url(request: Request, **extra: str | None) -> str:
    """``/`` with the caller's scenario/at plus ``extra``; empty values dropped."""
    from urllib.parse import urlencode

    q = {k: v for k, v in request.query_params.items() if k in ("scenario", "at")}
    q.update({k: v for k, v in extra.items() if v})
    q = {k: v for k, v in q.items() if v}
    return "/" + (f"?{urlencode(q)}" if q else "")


@router.get("/playback")
def playback(request: Request) -> RedirectResponse:
    """Playback is now Monitor at ``/``; old links keep their scenario and time."""
    return RedirectResponse(_monitor_url(request), status_code=307)


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


@router.get("/dashboard/facilities/{facility_id}")
def facility_page(request: Request, facility_id: str) -> RedirectResponse:
    """A facility is read in Monitor's focus layout; the old page URL lands there with the
    same scenario and time."""
    if get_facility(_engine(request), facility_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown facility {facility_id}")
    return RedirectResponse(_monitor_url(request, facility=facility_id), status_code=307)


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
    anchors = _anchor_classifications()
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
        show_asof=False,
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


parse_iso = datetime.fromisoformat


def warm_replay_caches(engine: Engine) -> None:
    """Fill the per-replay caches behind the Scenarios and Cards pages, so the first visitor
    after a deploy does not pay for them. Called from the app's startup thread."""
    from xevents.api import scenario_summary  # local import avoids a circular import

    for name in list_scenarios():
        _replay_stats(engine, name)
        start = datetime.fromisoformat(scenario_summary(name)["window_start"])
        _card_firing(engine, name, start)


def _live_summary(engine: Engine, cards: dict[str, Any]) -> dict[str, Any]:
    """What the live scenario holds right now, computed from the live rows: the Monitor window
    (two weeks back, up to a week ahead), events in it by source, what fires now and what
    fired over the window, and when the feeds last ran."""
    now = datetime.now(UTC)
    start, end = now - timedelta(days=14), now + timedelta(days=7)
    events = [
        e
        for e in compact_events(engine, live_only=True)
        if parse_iso(e["expires"]) >= start and parse_iso(e["onset"]) <= end
    ]
    by_source: dict[str, int] = {}
    for e in events:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
    items = [
        i
        for i in action_item_facts(engine, live_only=True, role=Role.CARE_TEAM.value)
        if i["window_end"] >= start and i["window_start"] <= end
    ]
    now_items = [i for i in items if i["window_start"] <= now <= i["window_end"]]

    def by_number(ids: set[str]) -> list[Any]:
        return sorted((cards[c] for c in ids if c in cards), key=lambda c: c.number)

    runs = latest_feed_runs(engine)
    last = max((r["run_at"] for r in runs), default=None)
    return {
        "window_start": start,
        "window_end": end,
        "events": len(events),
        "events_now": sum(
            1 for e in events if parse_iso(e["onset"]) <= now <= parse_iso(e["expires"])
        ),
        "forecast_ahead": sum(1 for e in events if parse_iso(e["onset"]) > now),
        "by_source": sorted(by_source.items(), key=lambda kv: -kv[1]),
        "cards_now": by_number({i["card_id"] for i in now_items}),
        "cards_window": by_number({i["card_id"] for i in items}),
        "facilities_now": len({i["scope_id"] for i in now_items}),
        "facilities_window": len({i["scope_id"] for i in items}),
        "last_run": datetime.fromisoformat(last) if last else None,
        "problems": [r["provider"] for r in runs if r["status"] == "failed"],
        "partial": [s for s in load_registry().sources if s.live.coverage_level == "partial"],
    }


_STATS_CACHE: dict[tuple[object, ...], Any] = {}


def _per_replay(kind: str, engine: Engine, scenario: str, build: Any) -> Any:
    """Memoise a per-replay computation on the replay's row fingerprint: replays change only
    on re-ingest, re-match or a status change, so pages stop recomputing them per request."""
    key = (kind, scenario, replay_version(engine, scenario))
    if key not in _STATS_CACHE:
        if len(_STATS_CACHE) > 64:
            _STATS_CACHE.clear()
        _STATS_CACHE[key] = build()
    return _STATS_CACHE[key]


def _replay_stats(engine: Engine, scenario: str) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        facts = action_item_facts(engine, scenario=scenario, include_superseded=True)
        numbers = {c.id: c.number for c in load_cards()}
        return {
            "card_ids": sorted({f["card_id"] for f in facts}, key=lambda c: numbers.get(c, 99)),
            "facilities": len({f["scope_id"] for f in facts}),
            "item_count": sum(1 for f in facts if f["status"] != ActionItemStatus.SUPERSEDED.value),
        }

    return dict(_per_replay("stats", engine, scenario, build))


@router.get("/replays", response_class=HTMLResponse)
def replays_page(request: Request) -> HTMLResponse:
    """Scenarios: what each replay is, what it exercises, and moments worth looking at, each
    a deep link into Monitor. Stats are computed from the fixtures and stored items."""
    ctx = _context(request, None, None)
    engine = _engine(request)
    guide = load_guide()
    summaries = {s["id"]: s for s in ctx["scenarios"]}
    cards = {c.id: c for c in load_cards()}
    rows: list[dict[str, Any]] = []
    for r in guide.replays:
        summary = summaries.get(r.id)
        if summary is None:
            continue
        stats = _replay_stats(engine, r.id)
        rows.append(
            {
                "guide": r,
                "summary": summary,
                "cards": [cards[c] for c in stats["card_ids"] if c in cards],
                "facilities": stats["facilities"],
                "item_count": stats["item_count"],
            }
        )
    ctx.update(
        show_asof=False,
        show_banner=False,
        replays=rows,
        cataloged=guide.cataloged,
        cards_by_id=cards,
        live=_live_summary(engine, cards),
        live_guide=guide.live,
    )
    return templates.TemplateResponse(request, "replays.html", ctx)


def _card_firing(
    engine: Engine, scenario: str, window_start: datetime
) -> dict[str, dict[str, Any]]:
    """card id → where and when it fires in one replay: facilities reached, first time, and
    the peak hour (most facilities at once) — the moment Monitor should open on. Care-team
    items only, superseded ones excluded, as Monitor shows them. Memoised per replay on its
    row fingerprint (``_per_replay``)."""

    def build() -> dict[str, dict[str, Any]]:
        facts = action_item_facts(engine, scenario=scenario, role=Role.CARE_TEAM.value)
        by_card: dict[str, list[dict[str, Any]]] = {}
        for f in facts:
            by_card.setdefault(f["card_id"], []).append(f)
        out: dict[str, dict[str, Any]] = {}
        for card_id, its in by_card.items():
            # candidate moments: each item's opening hour, not before the replay's first
            # onset (Monitor's timeline starts there)
            starts = sorted(
                {max(i["window_start"], window_start).replace(minute=0, second=0) for i in its}
            )
            best, best_n = starts[0], -1
            for t in starts:
                n = len({i["scope_id"] for i in its if i["window_start"] <= t <= i["window_end"]})
                if n > best_n:
                    best, best_n = t, n
            out[card_id] = {
                "facilities": len({i["scope_id"] for i in its}),
                "first": min(i["window_start"] for i in its),
                "peak": best,
                "peak_facilities": best_n,
            }
        return out

    result: dict[str, dict[str, Any]] = _per_replay("firing", engine, scenario, build)
    return result


def _cards_context(request: Request) -> dict[str, Any]:
    """Shared by the card overview and detail pages: the card models plus what the system
    computes about them (acuity position, hooks, where each fires, live now)."""
    ctx = _context(request, None, None)
    engine = _engine(request)
    profile = load_profile(PROFILES_DIR / "va.yaml")
    cards = sorted(load_cards(), key=lambda c: c.number)
    firing: dict[str, list[dict[str, Any]]] = {c.id: [] for c in cards}
    for s in ctx["scenarios"]:
        start = datetime.fromisoformat(s["window_start"])
        for card_id, f in _card_firing(engine, s["id"], start).items():
            firing.setdefault(card_id, []).append({"scenario": s["id"], **f})
    now = datetime.now(UTC)
    live: dict[str, set[str]] = {}
    for i in action_item_facts(engine, live_only=True, active_at=now, role=Role.CARE_TEAM.value):
        live.setdefault(i["card_id"], set()).add(i["scope_id"])
    ctx.update(
        show_asof=False,
        show_banner=False,
        cards=cards,
        firing=firing,
        live_now={k: len(v) for k, v in live.items()},
        acuity_order=profile.acuity_order,
        hooks=profile.hooks,
        escalation_default=profile.escalation_default,
        carbon_disclaimer=carbon_table().ui_disclaimer,
    )
    return ctx


@router.get("/card-library", response_class=HTMLResponse)
def card_library(request: Request) -> HTMLResponse:
    """Cards: the eight playbook cards at a glance — what triggers each, whom it selects, how
    strong its evidence is, and where it fires in the replays and live now."""
    return templates.TemplateResponse(request, "card_library.html", _cards_context(request))


@router.get("/card-library/{card_id}", response_class=HTMLResponse)
def card_detail(request: Request, card_id: str) -> HTMLResponse:
    """One card in full, verbatim from its YAML: triggers, population, both audiences'
    actions, escalation, evidence with tiers, sources, carbon, and where it fires."""
    ctx = _cards_context(request)
    card = next((c for c in ctx["cards"] if c.id == card_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail=f"unknown card {card_id}")
    ctx.update(
        card=card,
        carbon=carbon_for(card.number),
        safety=safety_message(card, load_profile(PROFILES_DIR / "va.yaml")),
    )
    return templates.TemplateResponse(request, "card_detail.html", ctx)
