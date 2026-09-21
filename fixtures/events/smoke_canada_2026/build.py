"""Build the July 2026 Canadian-wildfire smoke replay scenario (Upper Midwest / Great Lakes
-> Northeast, July 14-20, 2026), with the concurrent central-US heat dome for narrative.

Sources (all public, no key; retrieved 2026-09-21; raw copies in ``raw/``):
- NOAA HMS daily smoke polygon shapefiles, 2026-07-14 .. 07-20 (observed smoke density).
- AirNow public file archive ``files.airnowtech.org/airnow/2026/<YYYYMMDD>/daily_data_v2.dat``
  (daily site AQI for PM2.5 24-h and ozone 8-h; the keyless route that replaces the
  key-gated API for historical pulls). Sites -> counties by point-in-polygon; one event per
  (day, county, parameter) at AQI >= 101.
- IEM NWS VTEC archive CSV, 2026-07-13 -> 2026-07-21, heat products EH/XH/HT (W/A/Y),
  filtered to the affected states.
Expected replay outcome: Card 8 for Midwest/Great Lakes/Northeast facilities from AQI and
HMS Medium/Heavy smoke; Cards 1/2/4 where heat products co-occur.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import download, iem_csv, write_events

from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import UgcResolver
from xevents.models import EventType
from xevents.providers.airnow import parse_daily_data_v2, parse_observations
from xevents.providers.hms import BASE_URL as HMS_BASE
from xevents.providers.hms import parse_smoke
from xevents.providers.iem_archive import parse_iem_csv

SCENARIO = "smoke_canada_2026"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DAYS = [date(2026, 7, 14) + timedelta(days=i) for i in range(7)]
AIRNOW_ARCHIVE = "https://files.airnowtech.org/airnow"
# Central-US heat dome + smoke corridor: Upper Midwest, Great Lakes, Ohio Valley,
# Mid-Atlantic, Northeast
STATES = {
    "MN", "WI", "MI", "IL", "IN", "OH", "IA", "MO", "KS", "NE", "OK", "KY", "TN", "WV",
    "PA", "NY", "NJ", "MD", "DC", "DE", "VA", "CT", "MA", "RI", "VT", "NH", "ME",
}  # fmt: skip


def main() -> int:
    counties = CountyIndex.load()
    events = []
    for day in DAYS:
        name = f"hms_smoke{day:%Y%m%d}.zip"
        path = download(f"{HMS_BASE}/{day:%Y}/{day:%m}/{name}", RAW / name)
        for e in parse_smoke(
            path.read_bytes(), day, counties, raw_ref=f"fixtures/events/{SCENARIO}/raw/{name}"
        ):
            events.append(e.model_copy(update={"scenario": SCENARIO}))
    smoke = len(events)
    for day in DAYS:
        name = f"airnow_daily_data_v2_{day:%Y%m%d}.dat"
        path = download(f"{AIRNOW_ARCHIVE}/{day:%Y}/{day:%Y%m%d}/daily_data_v2.dat", RAW / name)
        rows = parse_daily_data_v2(path.read_text(encoding="utf-8", errors="replace"), day)
        for e in parse_observations(
            rows, counties, raw_ref=f"fixtures/events/{SCENARIO}/raw/{name}"
        ):
            if e.geography.states and e.geography.states[0] in STATES:
                events.append(e.model_copy(update={"scenario": SCENARIO}))
    aqi = len(events) - smoke
    csv_path = iem_csv(
        RAW / "iem_watchwarn_2026-07-13_2026-07-21_EH-XH-HT.csv",
        start="2026-07-13T00:00Z",
        end="2026-07-21T00:00Z",
        phenomena="EH,XH,HT",
        significance="W,A,Y",
    )
    # IEM ignores the phenomena filter, so the nationwide CSV also holds flood products;
    # this scenario's NWS layer is the heat dome only.
    heat = [
        e
        for e in parse_iem_csv(
            csv_path,
            UgcResolver.load(),
            scenario=SCENARIO,
            states=STATES,
            raw_ref=f"fixtures/events/{SCENARIO}/raw/{csv_path.name}",
        )
        if e.event_type is EventType.HEAT
    ]
    events.extend(heat)
    print(
        f"{smoke} HMS smoke events, {aqi} AirNow county-day AQI events, {len(heat)} NWS heat events"
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
