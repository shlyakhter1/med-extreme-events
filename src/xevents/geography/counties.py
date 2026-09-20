"""County boundaries + point-in-polygon lookup (pure Python; ~3,200 generalized polygons).

Loads ``fixtures/reference/counties.geojson`` built by ``scripts/build_county_boundaries.py``.
Ray casting with a per-feature bbox prefilter is plenty for facility-scale lookups.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = REPO_ROOT / "fixtures" / "reference" / "counties.geojson"

Ring = list[tuple[float, float]]


@dataclass(frozen=True)
class County:
    geoid: str
    name: str
    state: str


@dataclass(frozen=True)
class _Shape:
    county: County
    bbox: tuple[float, float, float, float]
    polygons: list[list[Ring]]  # each polygon: [outer, hole, hole, ...]


def _point_in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(x: float, y: float, polygon: list[Ring]) -> bool:
    if not _point_in_ring(x, y, polygon[0]):
        return False
    return not any(_point_in_ring(x, y, hole) for hole in polygon[1:])


def _rep_point_of_shape(shape: _Shape) -> tuple[float, float]:
    """Representative point: vertex centroid of the largest outer ring (good enough for
    nearest-facility distance and polygon coverage tests)."""
    outer = max((poly[0] for poly in shape.polygons), key=len)
    n = len(outer)
    return (sum(p[0] for p in outer) / n, sum(p[1] for p in outer) / n)


class CountyIndex:
    def __init__(self, shapes: list[_Shape], source: str) -> None:
        self._shapes = shapes
        self.source = source

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> CountyIndex:
        doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        shapes: list[_Shape] = []
        for feat in doc["features"]:
            geom = feat["geometry"]
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            props = feat["properties"]
            shapes.append(
                _Shape(
                    county=County(props["geoid"], props["name"], props["state"]),
                    bbox=tuple(feat["bbox"]),
                    polygons=[
                        [[(float(x), float(y)) for x, y in ring] for ring in poly] for poly in polys
                    ],
                )
            )
        prov = doc.get("provenance", {})
        source = f"{prov.get('source', path.name)} ({prov.get('retrieved', 'n/a')})"
        return cls(shapes, source)

    def __len__(self) -> int:
        return len(self._shapes)

    def shapes(self) -> list[_Shape]:
        return self._shapes

    def ids(self) -> set[str]:
        return {s.county.geoid for s in self._shapes}

    @property
    def states(self) -> frozenset[str]:
        """USPS codes of every state/territory with county coverage."""
        return frozenset(s.county.state for s in self._shapes)

    def lookup(self, lon: float, lat: float) -> County | None:
        for s in self._shapes:
            x0, y0, x1, y1 = s.bbox
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if any(_point_in_polygon(lon, lat, poly) for poly in s.polygons):
                return s.county
        return None
