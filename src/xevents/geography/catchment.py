"""County → facility catchment (Mode A).

Every county is assigned to the nearest *anchor* facility (great-circle distance from the
county's representative point to the facility), where anchor classifications come from the
profile (VA: medical centers, health care centers, CBOCs). A facility's catchment is the set
of counties assigned to it, so veterans are never double counted across facilities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from xevents.geography.counties import CountyIndex, _rep_point_of_shape
from xevents.models import Facility

EARTH_KM = 6371.0088


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class CatchmentAssignment:
    county_fips: str
    facility_id: str
    distance_km: float


@dataclass(frozen=True)
class StationAssignment:
    """Which anchor station sizes a facility's panel."""

    facility_id: str
    station_id: str
    method: str  # 'self' | 'health_care_system' | 'nearest'


def is_anchor(f: Facility, anchor_classifications: list[str]) -> bool:
    cls = f.classification or ""
    return any(cls.startswith(a) for a in anchor_classifications)


def assign_stations(
    facilities: list[Facility], anchor_classifications: list[str]
) -> list[StationAssignment]:
    anchors = [f for f in facilities if is_anchor(f, anchor_classifications)]
    by_system: dict[str, list[Facility]] = {}
    for a in anchors:
        if a.health_care_system:
            by_system.setdefault(a.health_care_system, []).append(a)
    out = []
    for f in facilities:
        if is_anchor(f, anchor_classifications):
            out.append(StationAssignment(f.id, f.id, "self"))
            continue
        candidates = by_system.get(f.health_care_system or "", [])
        method = "health_care_system" if candidates else "nearest"
        pool = candidates or anchors
        best = min(pool, key=lambda a: haversine_km(f.lon, f.lat, a.lon, a.lat))
        out.append(StationAssignment(f.id, best.id, method))
    return out


def assign_catchments(
    facilities: list[Facility],
    counties: CountyIndex,
    anchor_classifications: list[str],
) -> list[CatchmentAssignment]:
    anchors = [
        f
        for f in facilities
        if f.classification
        and any(f.classification.startswith(a) for a in anchor_classifications)
        and f.county_fips is not None
    ]
    if not anchors:
        raise ValueError("no anchor facilities match the profile's anchor classifications")
    out: list[CatchmentAssignment] = []
    for shape in counties.shapes():
        lon, lat = _rep_point_of_shape(shape)
        best: tuple[float, Facility] | None = None
        for f in anchors:
            # cheap prefilter: skip anchors more than ~15° away in either axis
            if abs(f.lat - lat) > 15 or abs(f.lon - lon) > 15:
                continue
            d = haversine_km(lon, lat, f.lon, f.lat)
            if best is None or d < best[0]:
                best = (d, f)
        if best is None:  # remote territory: fall back to a global search
            best = min(
                ((haversine_km(lon, lat, f.lon, f.lat), f) for f in anchors), key=lambda t: t[0]
            )
        out.append(CatchmentAssignment(shape.county.geoid, best[1].id, round(best[0], 1)))
    return out
