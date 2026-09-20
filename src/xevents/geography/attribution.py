"""Attribute each facility to a county and VISN.

County: point-in-polygon on the facility coordinates (primary; facilities always carry L3
points), falling back to the physical-address ZIP → county crosswalk. VISN: the Facilities
API's own ``visn`` attribute. Every attribution records how it was made in ``county_source``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xevents.geography.counties import CountyIndex
from xevents.geography.zip_county import ZipCountyCrosswalk
from xevents.models import Facility


@dataclass
class AttributionReport:
    facilities: list[Facility]
    unresolved_county: list[str] = field(default_factory=list)
    unresolved_visn: list[str] = field(default_factory=list)
    by_method: dict[str, int] = field(default_factory=dict)

    @property
    def all_resolved(self) -> bool:
        return not self.unresolved_county and not self.unresolved_visn


def attribute_facilities(
    facilities: list[Facility],
    crosswalk: ZipCountyCrosswalk,
    counties: CountyIndex | None = None,
) -> AttributionReport:
    out: list[Facility] = []
    report = AttributionReport(facilities=out)
    for f in facilities:
        county_fips: str | None = None
        source: str | None = None
        if counties is not None:
            hit = counties.lookup(f.lon, f.lat)
            if hit is not None:
                county_fips = hit.geoid
                source = (
                    f"point-in-polygon ({f.lon}, {f.lat}) → {hit.name}, {hit.state}; "
                    f"{counties.source}"
                )
                report.by_method["point_in_polygon"] = (
                    report.by_method.get("point_in_polygon", 0) + 1
                )
        if county_fips is None:
            match = crosswalk.lookup(f.zip5)
            if match is not None:
                county_fips = match.county_fips
                source = f"zip {f.zip5} → county (share {match.share:.2f}; {match.source})"
                report.by_method["zip_crosswalk"] = report.by_method.get("zip_crosswalk", 0) + 1
        if county_fips is None:
            report.unresolved_county.append(f.id)
            updated = f
        else:
            updated = f.model_copy(update={"county_fips": county_fips, "county_source": source})
        if updated.visn is None:
            report.unresolved_visn.append(f.id)
        out.append(updated)
    return report
