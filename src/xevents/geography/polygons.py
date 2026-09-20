"""Small polygon helpers shared by HMS smoke, AirNow monitors and zone geometry: which
counties does a GeoJSON polygon cover? Pure Python, approximate by design (documented
simplification per docs/implementation-plan.md §6 risks): a county is covered when its
representative point lies inside the polygon or any polygon vertex lies inside the county.
"""

from __future__ import annotations

from typing import Any

from xevents.geography.counties import CountyIndex, _point_in_polygon

Ring = list[tuple[float, float]]


def _polygons(geometry: dict[str, Any]) -> list[list[Ring]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    raw = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    return [[[(float(x), float(y)) for x, y in ring] for ring in poly] for poly in raw]


def _bbox(polys: list[list[Ring]]) -> tuple[float, float, float, float]:
    pts = [pt for poly in polys for ring in poly for pt in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _rep_point(poly: list[Ring]) -> tuple[float, float]:
    outer = poly[0]
    n = len(outer)
    return (sum(p[0] for p in outer) / n, sum(p[1] for p in outer) / n)


def counties_covered(geometry: dict[str, Any], counties: CountyIndex) -> list[str]:
    """County FIPS approximately intersecting ``geometry`` (Polygon or MultiPolygon)."""
    polys = _polygons(geometry)
    if not polys:
        return []
    gx0, gy0, gx1, gy1 = _bbox(polys)
    found: set[str] = set()
    for shape in counties.shapes():
        cx0, cy0, cx1, cy1 = shape.bbox
        if cx1 < gx0 or cx0 > gx1 or cy1 < gy0 or cy0 > gy1:
            continue
        # county representative point inside the geometry?
        for cpoly in shape.polygons:
            rx, ry = _rep_point(cpoly)
            if any(_point_in_polygon(rx, ry, gpoly) for gpoly in polys):
                found.add(shape.county.geoid)
                break
        if shape.county.geoid in found:
            continue
        # any geometry vertex inside the county?
        for gpoly in polys:
            for ring in gpoly:
                if any(
                    cx0 <= vx <= cx1 and cy0 <= vy <= cy1 and _point_in_polygon(vx, vy, cpoly)
                    for vx, vy in ring[:: max(1, len(ring) // 200)]
                    for cpoly in shape.polygons
                ):
                    found.add(shape.county.geoid)
                    break
            if shape.county.geoid in found:
                break
    return sorted(found)
