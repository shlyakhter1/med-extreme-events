"""FastAPI routes. M1: health check and the facilities map endpoint (GeoJSON)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from sqlalchemy import Engine

from xevents import __version__
from xevents.providers.va_facilities import to_geojson
from xevents.store import get_facility, list_facilities, make_engine


def create_app(engine: Engine | None = None) -> FastAPI:
    app = FastAPI(title="med-extreme-events", version=__version__)
    app.state.engine = engine or make_engine()

    def _engine(request: Request) -> Engine:
        eng: Engine = request.app.state.engine
        return eng

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

    return app


app = create_app()
