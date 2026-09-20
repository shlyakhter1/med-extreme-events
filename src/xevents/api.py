"""FastAPI routes. M1: health check and the facilities map endpoint (GeoJSON)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from xevents import __version__
from xevents.cards import load_cards
from xevents.denominators import PanelEstimator, ReferenceTables
from xevents.models import ActionItemStatus
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.replay import list_scenarios, load_scenario
from xevents.providers.va_facilities import to_geojson
from xevents.store import (
    TransitionError,
    catchment_map,
    get_action_item,
    get_facility,
    list_action_items,
    list_events,
    list_facilities,
    make_engine,
    station_map,
    transition_action_item,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COUNTIES_GEOJSON = REPO_ROOT / "fixtures" / "reference" / "counties.geojson"
WEB_DIR = Path(__file__).resolve().parent / "web"


class StatusChange(BaseModel):
    status: ActionItemStatus


def _parse_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"bad timestamp {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def create_app(engine: Engine | None = None) -> FastAPI:
    app = FastAPI(title="med-extreme-events", version=__version__)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
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
        out = []
        for name in list_scenarios():
            evs = load_scenario(name)
            out.append(
                {
                    "id": name,
                    "events": len(evs),
                    "window_start": min(e.onset for e in evs).isoformat(),
                    "window_end": max(e.expires for e in evs).isoformat(),
                    "event_types": sorted({e.event_type.value for e in evs}),
                }
            )
        return out

    @app.get("/events")
    def events(
        request: Request,
        scenario: str | None = Query(default=None, description="replay scenario id; omit for live"),
        at: str | None = Query(default=None, description="ISO timestamp; only events active then"),
        county: str | None = Query(default=None, pattern=r"^\d{5}$"),
        include_polygons: bool = Query(default=False),
    ) -> dict[str, Any]:
        rows = list_events(
            _engine(request), scenario=scenario, active_at=_parse_at(at), county_fips=county
        )
        if scenario is None:
            rows = [e for e in rows if e.scenario is None]
        exclude = None if include_polygons else {"geography": {"polygon"}}
        return {
            "count": len(rows),
            "events": [e.model_dump(mode="json", exclude=exclude) for e in rows],
        }

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
            "events": [e.model_dump(mode="json", exclude={"geography": {"polygon"}}) for e in rows],
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
    ) -> dict[str, Any]:
        rows = list_action_items(
            _engine(request),
            scenario=scenario,
            facility_id=facility,
            role=role,
            card_id=card,
            status=status,
            active_at=_parse_at(at),
            include_superseded=include_superseded,
        )
        if scenario is None:
            rows = [i for i in rows if i.scenario is None]
        if compact:
            items = [
                {
                    "id": i.id,
                    "event_key": i.event_key,
                    "event_name": i.event_name,
                    "event_type": i.event_type.value,
                    "event_severity": i.event_severity.value,
                    "card_id": i.card_id,
                    "card_title": i.card_title,
                    "facility_id": i.scope_id,
                    "role": i.role.value,
                    "status": i.status.value,
                    "superseded_by": i.superseded_by,
                    "acuity_rank": i.acuity_rank,
                    "acuity_class": i.acuity_class,
                    "panel": round(i.panel.value) if i.panel else None,
                    "window_start": i.window_start.isoformat(),
                    "window_end": i.window_end.isoformat(),
                }
                for i in rows
            ]
        else:
            items = [i.model_dump(mode="json") for i in rows]
        return {"count": len(items), "items": items}

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
            facility_id=facility_id,
            role=role,
            active_at=_parse_at(at),
        )
        if scenario is None:
            rows = [i for i in rows if i.scenario is None]
        return {"count": len(rows), "items": [i.model_dump(mode="json") for i in rows]}

    # ------------------------------------------------------------------ cards & reference

    @app.get("/cards")
    def cards() -> list[dict[str, Any]]:
        return [c.model_dump(mode="json") for c in load_cards()]

    @app.get("/reference/counties")
    def counties() -> FileResponse:
        return FileResponse(COUNTIES_GEOJSON, media_type="application/geo+json")

    @app.get("/playback", response_class=HTMLResponse)
    def playback() -> str:
        return (WEB_DIR / "templates" / "playback.html").read_text(encoding="utf-8")

    @app.get("/static/playback.js")
    def playback_js() -> FileResponse:
        return FileResponse(WEB_DIR / "static" / "playback.js", media_type="application/javascript")

    return app


app = create_app()
