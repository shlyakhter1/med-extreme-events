"""Build the 2021 Pacific Northwest heat dome replay scenario (June 25 - July 1, 2021).

Sources (all public, retrieved 2026-09-20; raw copies in ``raw/``):
- IEM NWS VTEC archive, watch/warning/advisory CSV, 2021-06-24 -> 2021-07-02, phenomena
  EH/HT, significance W/Y/A (nationwide file, filtered to WA/OR/ID here).
- IEM NWS zone geometries valid 2021-06-27 for OR, WA, ID — the 2021 public-zone numbering
  (e.g. ORZ006, WAZ558) predates the 2024-2026 renumbering, so zone -> county is derived from
  dated geometry, falling back to the current NWS zone-county file.
Expected replay outcome: Cards 1, 2, 4 fire for WA/OR facilities.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iem_csv, iem_zones, write_events

from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import UgcResolver
from xevents.providers.iem_archive import parse_iem_csv, resolver_from_zone_geojson

SCENARIO = "heat_dome_2021"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
STATES = {"WA", "OR", "ID"}
VALID = "2021-06-27T00:00Z"


def main() -> int:
    csv_path = iem_csv(
        RAW / "iem_watchwarn_2021-06-24_2021-07-02_EH-HT.csv",
        start="2021-06-24T00:00Z",
        end="2021-07-02T00:00Z",
        phenomena="EH,HT",
        significance="W,Y,A",
    )
    zone_paths = [
        iem_zones(RAW / f"iem_zones_{st}_2021-06-27.geojson", state=st, valid=VALID)
        for st in sorted(STATES)
    ]
    resolver = resolver_from_zone_geojson(zone_paths, CountyIndex.load(), base=UgcResolver.load())
    events = parse_iem_csv(
        csv_path,
        resolver,
        scenario=SCENARIO,
        states=STATES,
        raw_ref=f"fixtures/events/{SCENARIO}/raw/{csv_path.name}",
    )
    unresolved = [e.source_id for e in events if not e.geography.county_fips]
    if unresolved:
        print(
            f"WARNING: {len(unresolved)} events without counties: {unresolved[:5]}", file=sys.stderr
        )
    write_events(HERE, events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
