"""Build the Hurricane Ian replay scenario (Florida, September 24 - 30, 2022).

Sources (all public, retrieved 2026-09-20; raw copies in ``raw/``):
- IEM NWS VTEC archive CSV, 2022-09-24 -> 2022-09-30, phenomena HU/TR/SS/FF/FA, significance
  W/A (nationwide file, filtered to FL here).
- OpenFEMA DisasterDeclarationsSummaries for DR-4673 (67 designated counties).
- IEM NWS zone geometries valid 2022-09-27 for FL (two 2022 zones are absent from the
  current zone-county file).
- (M10 upgrade) ORNL EAGLE-I 2022 county outages (figshare doi:10.6084/m9.figshare.24237376,
  ``eaglei_outages_2022.csv``, 1.2 GB): the Florida slice for 2022-09-26 .. 10-03 is kept as
  ``raw/eaglei_2022_FL_2022-09-26_2022-10-03.csv`` (15-minute cadence, normalized columns),
  produced with ``--slice-from /path/to/eaglei_outages_2022.csv``; events are hourly maxima.
Expected replay outcome: Cards 3, 5, 6 fire for Florida facilities from the watches and
warnings, dialysis ranked first; once EAGLE-I outages land (observed, >= 10 % / 25 %,
two polls), the hurricane-watch items on Cards 3/5/6 are superseded by the outage items,
which carry during-event actions (the forecast -> observed supersede path).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import download, iem_csv, iem_zones, write_events

from xevents.cards import load_cards
from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import UgcResolver
from xevents.providers.eagle_i import (
    load_customers,
    load_ornl_events,
    min_outage_pct,
    slice_ornl_csv,
)
from xevents.providers.iem_archive import parse_iem_csv, resolver_from_zone_geojson
from xevents.providers.openfema import SELECT, parse_declarations

SCENARIO = "ian_2022"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FEMA_URL = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
OUTAGE_START, OUTAGE_END = datetime(2022, 9, 26, tzinfo=UTC), datetime(2022, 10, 3, tzinfo=UTC)
OUTAGE_SLICE = RAW / "eaglei_2022_FL_2022-09-26_2022-10-03.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slice-from",
        type=Path,
        default=None,
        help="path to ORNL eaglei_outages_2022.csv; writes the FL slice into raw/ first",
    )
    args = parser.parse_args()
    if args.slice_from is not None:
        n = slice_ornl_csv(
            args.slice_from, OUTAGE_SLICE, states={"Florida"}, start=OUTAGE_START, end=OUTAGE_END
        )
        print(f"sliced {n} ORNL rows into {OUTAGE_SLICE.name}")
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
    if OUTAGE_SLICE.exists():
        threshold = min_outage_pct(load_cards())
        assert threshold is not None
        outages = load_ornl_events(
            OUTAGE_SLICE,
            load_customers(),
            threshold_pct=threshold,
            scenario=SCENARIO,
            raw_ref=f"fixtures/events/{SCENARIO}/raw/{OUTAGE_SLICE.name}",
            start=OUTAGE_START,
            end=OUTAGE_END,
        )
        print(f"{len(outages)} hourly outage events >= {threshold}% of county customers")
        events.extend(outages)
    else:
        print(
            f"WARNING: {OUTAGE_SLICE.name} missing — no outage events (use --slice-from)",
            file=sys.stderr,
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
