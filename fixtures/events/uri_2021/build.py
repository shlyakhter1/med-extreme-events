"""Build the Winter Storm Uri replay scenario (Texas, February 10-20, 2021).

The headline v2 scenario: legacy NWS cold products (Wind Chill Warning/Watch/Advisory,
renamed by SCN23-44 in Oct 2024) exercise the provider's normalization, the largest US
outage in the EAGLE-I record fires Cards 3/5/6 from observed percent-out thresholds, and
the cold x outage co-occurrence boost lifts Card 7 items.

Sources (public; raw copies in ``raw/``):
- IEM NWS VTEC archive CSV, 2021-02-10 -> 2021-02-21, phenomena EC/CW/WS/IS/BZ/WC,
  significance W/A/Y (nationwide file, filtered to TX here; retrieved 2026-09-21).
- IEM NWS zone geometries valid 2021-02-15 for TX (2021 zone numbering).
- ORNL EAGLE-I 2021 county outages (figshare doi:10.6084/m9.figshare.24237376,
  ``eaglei_outages_2021.csv``, 1.1 GB): the Texas slice for the window is kept as
  ``raw/eaglei_2021_TX_2021-02-10_2021-02-21.csv`` (15-minute cadence, normalized columns),
  produced with ``--slice-from /path/to/eaglei_outages_2021.csv``; events are hourly maxima.
Expected replay outcome: Card 7 for TX facilities from cold products; Cards 3/5/6 from
observed outages >= 25 % / 10 % sustained two polls; boosted Card 7 items where both co-occur.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iem_csv, iem_zones, write_events

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

SCENARIO = "uri_2021"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
STATES = {"TX"}
START, END = datetime(2021, 2, 10, tzinfo=UTC), datetime(2021, 2, 21, tzinfo=UTC)
OUTAGE_SLICE = RAW / "eaglei_2021_TX_2021-02-10_2021-02-21.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slice-from",
        type=Path,
        default=None,
        help="path to ORNL eaglei_outages_2021.csv; writes the TX slice into raw/ first",
    )
    args = parser.parse_args()
    if args.slice_from is not None:
        n = slice_ornl_csv(args.slice_from, OUTAGE_SLICE, states={"Texas"}, start=START, end=END)
        print(f"sliced {n} ORNL rows into {OUTAGE_SLICE.name}")

    csv_path = iem_csv(
        RAW / "iem_watchwarn_2021-02-10_2021-02-21_EC-CW-WS-IS-BZ-WC.csv",
        start="2021-02-10T00:00Z",
        end="2021-02-21T00:00Z",
        phenomena="EC,CW,WS,IS,BZ,WC",
        significance="W,A,Y",
    )
    zone_path = iem_zones(
        RAW / "iem_zones_TX_2021-02-15.geojson", state="TX", valid="2021-02-15T00:00Z"
    )
    resolver = resolver_from_zone_geojson([zone_path], CountyIndex.load(), base=UgcResolver.load())
    events = parse_iem_csv(
        csv_path,
        resolver,
        scenario=SCENARIO,
        states=STATES,
        raw_ref=f"fixtures/events/{SCENARIO}/raw/{csv_path.name}",
    )
    legacy = sum(1 for e in events if "raw_nws_event" in e.metrics)
    print(f"{len(events)} NWS cold events ({legacy} carry a legacy product name)")

    if OUTAGE_SLICE.exists():
        threshold = min_outage_pct(load_cards())
        assert threshold is not None
        outages = load_ornl_events(
            OUTAGE_SLICE,
            load_customers(),
            threshold_pct=threshold,
            scenario=SCENARIO,
            raw_ref=f"fixtures/events/{SCENARIO}/raw/{OUTAGE_SLICE.name}",
            start=START,
            end=END,
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
