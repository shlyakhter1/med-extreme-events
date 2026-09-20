"""Build the Hurricane Ian replay scenario (Florida, September 24 - 30, 2022).

Sources (all public, retrieved 2026-09-20; raw copies in ``raw/``):
- IEM NWS VTEC archive CSV, 2022-09-24 -> 2022-09-30, phenomena HU/TR/SS/FF/FA, significance
  W/A (nationwide file, filtered to FL here).
- OpenFEMA DisasterDeclarationsSummaries for DR-4673 (67 designated counties).
- IEM NWS zone geometries valid 2022-09-27 for FL (two 2022 zones are absent from the
  current zone-county file).
Expected replay outcome: Cards 3, 5, 6 fire for Florida facilities, dialysis ranked first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import download, iem_csv, iem_zones, write_events

from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import UgcResolver
from xevents.providers.iem_archive import parse_iem_csv, resolver_from_zone_geojson
from xevents.providers.openfema import SELECT, parse_declarations

SCENARIO = "ian_2022"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FEMA_URL = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"


def main() -> int:
    csv_path = iem_csv(
        RAW / "iem_watchwarn_2022-09-24_2022-09-30_HU-TR-SS-FF-FA.csv",
        start="2022-09-24T00:00Z",
        end="2022-09-30T00:00Z",
        phenomena="HU,TR,SS,FF,FA",
        significance="W,A",
    )
    zone_path = iem_zones(
        RAW / "iem_zones_FL_2022-09-27.geojson", state="FL", valid="2022-09-27T00:00Z"
    )
    fema_path = download(
        FEMA_URL,
        RAW / "openfema_DR-4673.json",
        {"$filter": "disasterNumber eq 4673", "$top": "1000", "$select": SELECT},
    )
    resolver = resolver_from_zone_geojson([zone_path], CountyIndex.load(), base=UgcResolver.load())
    events = parse_iem_csv(
        csv_path,
        resolver,
        scenario=SCENARIO,
        states={"FL"},
        raw_ref=f"fixtures/events/{SCENARIO}/raw/{csv_path.name}",
    )
    rows = json.loads(fema_path.read_text(encoding="utf-8"))["DisasterDeclarationsSummaries"]
    for e in parse_declarations(rows, raw_ref=f"fixtures/events/{SCENARIO}/raw/{fema_path.name}"):
        events.append(e.model_copy(update={"scenario": SCENARIO}))
    unresolved = [e.source_id for e in events if not e.geography.county_fips]
    if unresolved:
        print(
            f"WARNING: {len(unresolved)} events without counties: {unresolved[:5]}", file=sys.stderr
        )
    write_events(HERE, events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
