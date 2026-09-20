"""Build the June 2023 Canadian-wildfire smoke replay scenario (NYC area, June 6 - 8, 2023).

Sources (public, retrieved 2026-09-20; raw copies in ``raw/``):
- NOAA HMS daily smoke polygon shapefiles for 2023-06-06/07/08.
Not included: NWS Air Quality Alerts (non-VTEC products, absent from the IEM VTEC archive;
the live NWS provider does capture them) and AirNow observations (historical pulls need an
API key - see PROGRESS.md).
Bonus scenario: no v1 card covers wildfire smoke; it exercises the smoke provider end to end.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import download, write_events

from xevents.geography.counties import CountyIndex
from xevents.providers.hms import BASE_URL as HMS_BASE
from xevents.providers.hms import parse_smoke

SCENARIO = "smoke_nyc_2023"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DAYS = [date(2023, 6, 6), date(2023, 6, 7), date(2023, 6, 8)]


def main() -> int:
    counties = CountyIndex.load()
    events = []
    for day in DAYS:
        name = f"hms_smoke{day:%Y%m%d}.zip"
        path = download(f"{HMS_BASE}/{day:%Y}/{day:%m}/{name}", RAW / name)
        raw_ref = f"fixtures/events/{SCENARIO}/raw/{name}"
        for e in parse_smoke(path.read_bytes(), day, counties, raw_ref=raw_ref):
            events.append(e.model_copy(update={"scenario": SCENARIO}))
    write_events(HERE, events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
