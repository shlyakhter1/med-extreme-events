"""FastAPI routes. M1: health check and the facilities map endpoint (GeoJSON)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from sqlalchemy import Engine

from xevents import __version__
from xevents.cards import load_cards
from xevents.denominators import PanelEstimator, ReferenceTables
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.va_facilities import to_geojson
from xevents.store import catchment_map, get_facility, list_facilities, make_engine, station_map


def create_app(engine: Engine | None = None) -> FastAPI:
    app = FastAPI(title="med-extreme-events", version=__version__)
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

    return app


app = create_app()
