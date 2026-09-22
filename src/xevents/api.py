"""FastAPI routes. M1: health check and the facilities map endpoint (GeoJSON)."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from functools import lru_cache, partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Engine

from xevents import __version__, live_refresh
from xevents.carbon import load_carbon
from xevents.cards import load_cards
from xevents.denominators import PanelEstimator, ReferenceTables
from xevents.models import ActionItemStatus, Event, EventSource
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.eagle_i import ATTRIBUTION, COVERAGE_CAVEAT, CUSTOMERS_CAVEAT
from xevents.providers.replay import EVENTS_DIR, list_scenarios, load_scenario
from xevents.providers.va_facilities import to_geojson
from xevents.store import (
    TransitionError,
    catchment_map,
    compact_action_items,
    compact_events,
    feed_status,
    get_action_item,
    get_event,
    get_facility,
    latest_feed_runs,
    list_action_items,
    list_events,
    list_facilities,
    make_engine,
    replay_version,
    station_map,
    transition_action_item,
)
from xevents.timeparse import BadTimestamp, parse_at

REPO_ROOT = Path(__file__).resolve().parents[2]
COUNTIES_GEOJSON = REPO_ROOT / "fixtures" / "reference" / "counties.geojson"
# Map-precision copy of the above, built alongside it; see _static_geo.
COUNTIES_DISPLAY_GEOJSON = REPO_ROOT / "fixtures" / "reference" / "counties.display.geojson"
STATES_GEOJSON = REPO_ROOT / "fixtures" / "reference" / "states.geojson"
COUNTRIES_GEOJSON = REPO_ROOT / "fixtures" / "reference" / "countries.geojson"
WEB_DIR = Path(__file__).resolve().parent / "web"


STALE_AFTER_HOURS = 6.0


class StatusChange(BaseModel):
    status: ActionItemStatus


def event_json(event: Event, *, include_polygon: bool = False) -> dict[str, Any]:
    """Serialize an event for the API. ``event_key`` is a Python property, so it is absent
    from ``model_dump()``; clients key on it, so put it back."""
    exclude = None if include_polygon else {"geography": {"polygon"}}
    doc = event.model_dump(mode="json", exclude=exclude)
    doc["event_key"] = event.event_key
    if event.source is EventSource.EAGLE_I:  # required wherever outage numbers render
        doc["attribution"] = ATTRIBUTION
        doc["caveats"] = [CUSTOMERS_CAVEAT, COVERAGE_CAVEAT]
    return doc


def scenario_summary(name: str) -> dict[str, Any]:
    """Window plus ``peak_at``: the hour with the most simultaneously active events, which
    the dashboard uses as its default "as of" moment for a replay. Every page computes this
    for every scenario, and Uri holds 13k events, so the result is cached per fixture file
    (invalidated when ``events.json`` changes) and the peak is found with one sweep."""
    path = EVENTS_DIR / name / "events.json"
    stat = path.stat()
    return dict(_scenario_summary(name, stat.st_mtime_ns, stat.st_size))


@lru_cache(maxsize=32)
def _scenario_summary(name: str, mtime_ns: int, size: int) -> dict[str, Any]:
    evs = load_scenario(name)
    start = min(e.onset for e in evs)
    end = max(e.expires for e in evs)
    last_onset = max(e.onset for e in evs)
    limit = min(end, last_onset + timedelta(days=3))
    hours = int((limit - start).total_seconds() // 3600) + 1
    # difference array over hourly steps t_k = start + k h: active iff onset <= t_k <= expires
    diff = [0] * (hours + 1)
    for e in evs:
        lo = math.ceil((e.onset - start).total_seconds() / 3600)
        hi = math.floor((e.expires - start).total_seconds() / 3600)
        lo, hi = max(lo, 0), min(hi, hours - 1)
        if lo <= hi:
            diff[lo] += 1
            diff[hi + 1] -= 1
    best_k, best_n, n = 0, -1, 0
    for k in range(hours):
        n += diff[k]
        if n > best_n:
            best_k, best_n = k, n
    return {
        "id": name,
        "events": len(evs),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "peak_at": (start + timedelta(hours=best_k)).isoformat(),
        "event_types": sorted({e.event_type.value for e in evs}),
        "sources": sorted({e.source.value for e in evs}),
    }


def _parse_at(value: str | None) -> datetime | None:
    try:
        return parse_at(value)
    except BadTimestamp as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the background live refresh when LIVE_REFRESH_MINUTES > 0 (hosted demo)."""
    minutes = live_refresh.minutes_from_env()
    if minutes:
        live_refresh.start(minutes)
        # hosted: warm the replay caches in the background so the first visitor after a
        # deploy is not the one who waits for them
        threading.Thread(
            target=_warm, args=(app.state.engine,), name="warm-caches", daemon=True
        ).start()
    yield


def _warm(engine: Engine) -> None:
    from xevents.web.views import warm_replay_caches  # local import: views imports api

    started = time.monotonic()
    try:
        for name in list_scenarios():
            version = replay_version(engine, name)
            _cache_body(
                _events_key(name, version),
                partial(_json_of, partial(_compact_events_doc, engine, name)),
            )
            _cache_body(
                _items_key(name, version),
                partial(_json_of, partial(_compact_items_doc, engine, name)),
            )
        warm_replay_caches(engine)
        print(
            f"cache warm-up: {len(list_scenarios())} replays in {time.monotonic() - started:.0f}s",
            flush=True,
        )
    except Exception as exc:  # warming is best-effort: a failure only means a slower first page
        print(f"cache warm-up failed: {type(exc).__name__}: {exc}", flush=True)


_BODY_CACHE: dict[tuple[object, ...], tuple[bytes, bytes, str]] = {}


def _cache_body(key: tuple[object, ...], build: Callable[[], bytes]) -> tuple[bytes, bytes, str]:
    """The (raw, gzipped, digest) body for ``key``, built, compressed and hashed once. The
    digest is the ETag: the key already determines the body, so a changed body is a new key."""
    hit = _BODY_CACHE.get(key)
    if hit is None:
        raw = build()
        hit = (raw, gzip.compress(raw, 6), hashlib.blake2b(raw, digest_size=16).hexdigest())
        if len(_BODY_CACHE) > 64:
            _BODY_CACHE.clear()
        _BODY_CACHE[key] = hit
    return hit


# Monitor's two replay requests, exactly as playback.js makes them (so the warm-up fills the
# same cache entries the page reads): /events?scenario=…&compact=1 and
# /action-items?scenario=…&include_superseded=true.
def _events_key(scenario: str, version: object) -> tuple[object, ...]:
    return ("events", scenario, None, None, False, True, version)


def _items_key(scenario: str, version: object) -> tuple[object, ...]:
    return ("items", scenario, None, None, True, True, version)


def _compact_events_doc(
    engine: Engine, scenario: str | None, active_at: datetime | None = None
) -> dict[str, Any]:
    docs = compact_events(
        engine, scenario=scenario, live_only=scenario is None, active_at=active_at
    )
    doc: dict[str, Any] = {"count": len(docs), "events": docs}
    if any(d["source"] == EventSource.EAGLE_I.value for d in docs):
        doc["eaglei"] = {"attribution": ATTRIBUTION, "caveats": [CUSTOMERS_CAVEAT, COVERAGE_CAVEAT]}
    return doc


def _compact_items_doc(
    engine: Engine,
    scenario: str | None,
    role: str | None = None,
    include_superseded: bool = True,
    active_at: datetime | None = None,
) -> dict[str, Any]:
    items = compact_action_items(
        engine,
        scenario=scenario,
        live_only=scenario is None,
        role=role,
        include_superseded=include_superseded,
        active_at=active_at,
    )
    return {"count": len(items), "items": items}


def _cached(
    request: Request,
    key: tuple[object, ...],
    build: Callable[[], bytes],
    media_type: str = "application/json",
    max_age: int | None = None,
    last_modified: datetime | None = None,
) -> Response:
    """Serve a body built once per ``key``, gzipped once. For responses that do not change
    between deploys or re-matches: replay scenarios (keyed on ``replay_version``) and the
    reference boundary files (keyed on file mtime). Encoding a 15 MB replay and gzipping it
    on every request is what made the hosted demo take tens of seconds."""
    raw, gz, digest = _cache_body(key, build)
    as_gzip = "gzip" in request.headers.get("accept-encoding", "")
    # Per-representation, so a cached gzip body is never matched against an identity one.
    etag = f'"{digest}{"-gz" if as_gzip else ""}"'
    headers = {"Vary": "Accept-Encoding", "ETag": etag}
    if max_age:
        headers["Cache-Control"] = f"public, max-age={max_age}"
    if last_modified is not None:
        headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)
    # Once max-age lapses the browser revalidates; without a validator that meant downloading
    # the whole boundary file again just to learn it had not changed.
    if etag in {t.strip() for t in request.headers.get("if-none-match", "").split(",")}:
        return Response(status_code=304, headers=headers)
    if as_gzip:
        return Response(gz, media_type=media_type, headers={**headers, "Content-Encoding": "gzip"})
    return Response(raw, media_type=media_type, headers=headers)


def _static_geo(request: Request, path: Path, display: Path | None = None) -> Response:
    """A reference boundary file, gzipped once and cacheable by the browser for a day (the
    files change only with a deploy): the map no longer re-downloads 2 MB on every visit.

    ``display`` is a smaller copy for the browser — geometry at map precision, without the
    bbox and properties only the server's county lookup reads. The full file stays the one
    ``CountyIndex`` joins facilities against, so thinning it cannot move a county line."""
    served = display if display is not None and display.exists() else path
    stat = served.stat()
    key = ("geo", str(served), stat.st_mtime_ns)
    return _cached(
        request,
        key,
        served.read_bytes,
        "application/geo+json",
        max_age=86400,
        last_modified=datetime.fromtimestamp(stat.st_mtime, UTC),
    )


def compact_item(i: Any) -> dict[str, Any]:
    """One item in the compact shape (same fields as ``store.compact_action_items``)."""
    return {
        "id": i.id,
        "event_key": i.event_key,
        "event_name": i.event_name,
        "event_type": i.event_type.value,
        "event_severity": i.event_severity.value,
        "event_temporality": i.event_temporality.value,
        "phase": i.phase.value,
        "card_id": i.card_id,
        "card_title": i.card_title,
        "facility_id": i.scope_id,
        "role": i.role.value,
        "status": i.status.value,
        "superseded_by": i.superseded_by,
        "acuity_rank": i.acuity_rank,
        "acuity_class": i.acuity_class,
        "panel": round(i.panel.value) if i.panel else None,
        "exposure": round(i.exposure.value) if i.exposure else None,
        "rank_score": round(i.rank_score, 1),
        "window_start": i.window_start.isoformat(),
        "window_end": i.window_end.isoformat(),
    }


def _json_of(build: Callable[[], Any]) -> bytes:
    return _json_bytes(build())


def _json_bytes(doc: Any) -> bytes:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()


def create_app(engine: Engine | None = None) -> FastAPI:
    app = FastAPI(title="med-extreme-events", version=__version__, lifespan=_lifespan)
    # Level 5: nearly the size of level 9 at a fraction of the CPU — on a small hosted CPU,
    # level 9 on megabyte responses cost seconds per request. Large, stable bodies are
    # pre-compressed once instead (``_cached``), and the middleware passes them through.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.state.engine = engine or make_engine()

    def _engine(request: Request) -> Engine:
        eng: Engine = request.app.state.engine
        return eng

    def _estimator(request: Request) -> PanelEstimator:
        est = getattr(request.app.state, "estimator", None)
        if est is None:
            profile = load_profile(PROFILES_DIR / "va.yaml")
            from xevents.geography.counties import CountyIndex

            tables = ReferenceTables.load(
                profile.catchment.projection_year, county_ids=CountyIndex.load().ids()
            )
            eng = _engine(request)
            est = PanelEstimator(profile, tables, catchment_map(eng), station_map(eng))
            request.app.state.estimator = est
        return est

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/facilities")
    def facilities(
        request: Request,
        state: str | None = Query(default=None, min_length=2, max_length=2),
        visn: str | None = Query(default=None, pattern=r"^\d{1,2}$"),
        county: str | None = Query(default=None, pattern=r"^\d{5}$"),
    ) -> dict[str, Any]:
        """GeoJSON FeatureCollection of health facilities with county/VISN attribution."""
        rows = list_facilities(_engine(request), state=state, visn=visn, county_fips=county)
        return to_geojson(rows)

    @app.get("/facilities/{facility_id}")
    def facility(request: Request, facility_id: str) -> dict[str, Any]:
        f = get_facility(_engine(request), facility_id)
        if f is None:
            raise HTTPException(status_code=404, detail=f"unknown facility {facility_id}")
        feature: dict[str, Any] = to_geojson([f])["features"][0]
        return feature

    @app.get("/facilities/{facility_id}/panels")
    def panels(
        request: Request, facility_id: str, card: str | None = Query(default=None)
    ) -> dict[str, Any]:
        """Sized panel per card (or one card) for a facility, with provenance."""
        f = get_facility(_engine(request), facility_id)
        if f is None:
            raise HTTPException(status_code=404, detail=f"unknown facility {facility_id}")
        cards = load_cards()
        if card is not None:
            cards = [c for c in cards if c.id == card]
            if not cards:
                raise HTTPException(status_code=404, detail=f"unknown card {card}")
        est = _estimator(request)
        return {
            "facility": f.model_dump(mode="json"),
            "veterans": est.veterans(facility_id).model_dump(mode="json"),
            "panels": {c.id: est.card_panel(facility_id, c).model_dump(mode="json") for c in cards},
        }

    # ------------------------------------------------------------------ events & scenarios

    @app.get("/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        """Replay scenarios with their time extent (from the fixture, not the store)."""
        return [scenario_summary(name) for name in list_scenarios()]

    @app.get("/feeds")
    def feeds(request: Request) -> dict[str, Any]:
        """Live feed freshness: per-source counts and last ingestion (for the banner)."""
        now = datetime.now(UTC)
        rows = feed_status(_engine(request))
        for r in rows:
            last = r["last_ingested_at"]
            age_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600 if last else None
            r["age_hours"] = round(age_h, 1) if age_h is not None else None
            r["stale"] = age_h is None or age_h > STALE_AFTER_HOURS
        return {
            "as_of": now.isoformat(),
            "stale_after_hours": STALE_AFTER_HOURS,
            "feeds": rows,
            "runs": latest_feed_runs(_engine(request)),
        }

    @app.get("/events")
    def events(
        request: Request,
        scenario: str | None = Query(default=None, description="replay scenario id; omit for live"),
        at: str | None = Query(default=None, description="ISO timestamp; only events active then"),
        county: str | None = Query(default=None, pattern=r"^\d{5}$"),
        include_polygons: bool = Query(default=False),
        compact: bool = Query(
            default=False,
            description="map/timeline fields only; EAGLE-I attribution once at the top level; "
            "full events at /events/detail",
        ),
    ) -> Any:
        eng = _engine(request)
        active_at = _parse_at(at)

        def build() -> dict[str, Any]:
            if compact and not county and not include_polygons:
                return _compact_events_doc(eng, scenario, active_at)
            rows = list_events(
                eng,
                scenario=scenario,
                active_at=active_at,
                county_fips=county,
                live_only=scenario is None,
            )
            return {
                "count": len(rows),
                "events": [event_json(e, include_polygon=include_polygons) for e in rows],
            }

        if scenario is not None:  # replays change only on re-ingest/re-match: cache the body
            key = (
                "events",
                scenario,
                at,
                county,
                include_polygons,
                compact,
                replay_version(eng, scenario),
            )
            return _cached(request, key, lambda: _json_bytes(build()))
        return build()

    @app.get("/events/detail")
    def event_detail(request: Request, key: str = Query(...)) -> dict[str, Any]:
        """One stored event by its natural key (``source:source_id``), polygon included."""
        ev = get_event(_engine(request), key)
        if ev is None:
            raise HTTPException(status_code=404, detail=f"unknown event {key}")
        return event_json(ev, include_polygon=True)

    @app.get("/events/active")
    def events_active(request: Request, county: str | None = Query(default=None)) -> dict[str, Any]:
        """Live events active now (scenario-less rows)."""
        now = datetime.now(UTC)
        rows = [
            e
            for e in list_events(_engine(request), active_at=now, county_fips=county)
            if e.scenario is None
        ]
        return {
            "as_of": now.isoformat(),
            "count": len(rows),
            "events": [event_json(e) for e in rows],
        }

    # ------------------------------------------------------------------ action items

    @app.get("/action-items")
    def action_items(
        request: Request,
        scenario: str | None = None,
        facility: str | None = None,
        role: str | None = None,
        card: str | None = None,
        status: str | None = None,
        at: str | None = None,
        include_superseded: bool = False,
        compact: bool = Query(
            default=True, description="omit card text; use /action-items/{id} for it"
        ),
    ) -> Any:
        eng = _engine(request)
        active_at = _parse_at(at)
        simple = not (facility or card or status)

        def build() -> dict[str, Any]:
            if compact and simple:  # the Monitor path: columns + stored payload, no validation
                return _compact_items_doc(eng, scenario, role, include_superseded, active_at)
            rows = list_action_items(
                eng,
                scenario=scenario,
                live_only=scenario is None,
                facility_id=facility,
                role=role,
                card_id=card,
                status=status,
                active_at=active_at,
                include_superseded=include_superseded,
            )
            if compact:
                items = [compact_item(i) for i in rows]
            else:
                items = [i.model_dump(mode="json") for i in rows]
            return {"count": len(items), "items": items}

        if scenario is not None and simple:
            key = (
                "items",
                scenario,
                role,
                at,
                include_superseded,
                compact,
                replay_version(eng, scenario),
            )
            return _cached(request, key, lambda: _json_bytes(build()))
        return build()

    @app.get("/action-items/{item_id:path}")
    def action_item(request: Request, item_id: str) -> dict[str, Any]:
        item = get_action_item(_engine(request), item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"unknown action item {item_id}")
        return item.model_dump(mode="json")

    @app.post("/action-items/{item_id:path}/status")
    def change_status(request: Request, item_id: str, change: StatusChange) -> dict[str, Any]:
        try:
            item = transition_action_item(_engine(request), item_id, change.status)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown action item {item_id}") from exc
        except TransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return item.model_dump(mode="json")

    @app.get("/facilities/{facility_id}/action-items")
    def facility_action_items(
        request: Request,
        facility_id: str,
        role: str | None = None,
        scenario: str | None = None,
        at: str | None = None,
    ) -> dict[str, Any]:
        rows = list_action_items(
            _engine(request),
            scenario=scenario,
            live_only=scenario is None,
            facility_id=facility_id,
            role=role,
            active_at=_parse_at(at),
        )
        return {"count": len(rows), "items": [i.model_dump(mode="json") for i in rows]}

    # ------------------------------------------------------------------ cards & reference

    @app.get("/cards")
    def cards() -> list[dict[str, Any]]:
        return [c.model_dump(mode="json") for c in load_cards()]

    @app.get("/carbon")
    def carbon() -> dict[str, Any]:
        """Display-only medication carbon-footprint estimates, grouped by card number.

        Order-of-magnitude figures from published life-cycle assessments; the table's own
        ``ui_disclaimer`` travels with the data so no caller can render a number without it.
        """
        table = load_carbon()
        doc = table.model_dump(mode="json")
        doc["by_card"] = {
            str(n): [
                {**e.model_dump(mode="json"), "citations": table.citations(e)}
                for e in table.for_card_number(n)
            ]
            for n in sorted({e.card for e in table.entries})
        }
        return doc

    @app.get("/reference/counties")
    def counties(request: Request) -> Response:
        return _static_geo(request, COUNTIES_GEOJSON, display=COUNTIES_DISPLAY_GEOJSON)

    @app.get("/reference/states")
    def states(request: Request) -> Response:
        """State and territory outlines for the map overlay (Census 1:5m, as the counties)."""
        return _static_geo(request, STATES_GEOJSON)

    @app.get("/reference/countries")
    def countries(request: Request) -> Response:
        """Neighbouring countries (Natural Earth 1:50m) — a basemap backdrop, no data."""
        return _static_geo(request, COUNTRIES_GEOJSON)

    from xevents.web.views import router as web_router

    app.include_router(web_router)

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    return app


app = create_app()
