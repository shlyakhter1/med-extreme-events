# Replay scenarios

Each `<scenario>/` holds raw archived source files (`raw/`), a `build.py` that turns them
into `events.json` (normalized `Event` records, the same model the live providers produce),
and the provenance below. Rebuild all with `make scenarios`; load with
`EVENT_MODE=replay make ingest` (each scenario's rows are replaced, keyed by `scenario`).

| Scenario | Window | Events | Sources (retrieved 2026-09-20) | Expected cards |
| --- | --- | --- | --- | --- |
| `heat_dome_2021` | 2021-06-25 → 07-08 | 20 NWS (8 Excessive Heat Warning, 8 Excessive Heat Watch, 4 Heat Advisory), 129 counties in WA/OR/ID | IEM NWS VTEC archive CSV (EH/HT, W/Y/A); IEM zone geometries valid 2021-06-27 for OR/WA/ID (2021 zone numbering predates the 2024–26 renumbering, so zone→county comes from dated geometry) | 1, 2, 4 for WA/OR facilities |
| `ian_2022` | 2022-09-23 → 11-04 | 66 NWS (hurricane/tropical storm/storm surge/flood watches & warnings) + 1 OpenFEMA DR-4673 (67 counties), 70 counties in FL | IEM NWS VTEC archive CSV (HU/TR/SS/FF/FA, W/A); IEM FL zone geometries valid 2022-09-27; OpenFEMA DisasterDeclarationsSummaries | 3, 5, 6 for FL facilities; dialysis first |
| `smoke_nyc_2023` | 2023-06-06 → 06-09 | 9 HMS smoke events (3 days × Light/Medium/Heavy); heavy smoke over NYC on June 7 | NOAA HMS daily smoke polygon shapefiles | 8 (from M9) for Northeast facilities |
| `uri_2021` (M10, **headline**) | 2021-02-10 → 02-21 | 78 NWS cold/winter events for TX (35 arrived as legacy Wind Chill products and are normalized, raw name in `metrics.raw_nws_event`) + 12,900 hourly EAGLE-I county outage events ≥ 10 % (211 counties; 1,796 hours clamped at 100 % with `outage_pct_raw` kept) | IEM NWS VTEC archive CSV (EC/CW/WS/IS/BZ/WC, W/A/Y; retrieved 2026-09-21); IEM TX zone geometries valid 2021-02-15; ORNL EAGLE-I 2021 county CSV (figshare `24237376`), Texas window sliced into `raw/` with `build.py --slice-from`, hourly maxima | 7 for TX facilities; 3/5/6 from observed outages; boosted 7 where both co-occur |
| `ian_2022` **upgrade** (M10) | + 2022-09-26 → 10-03 | + 1,756 hourly EAGLE-I FL outage events ≥ 10 % (59 hours clamped) | + ORNL EAGLE-I 2022 county CSV, Florida window sliced into `raw/` | hurricane-watch items on 3/5/6 superseded by observed-outage items (during-event actions) |
| `smoke_canada_2026` (M10) | 2026-07-13 → 07-21 | 21 HMS smoke events (7 days × 3 densities), 715 AirNow county-day AQI ≥ 101 events (PM2.5 24-h / ozone 8-h; max AQI 934) in 19 Midwest/Great Lakes/Mid-Atlantic/Northeast states, 82 NWS heat events (central-US heat dome; the nationwide IEM pull's flood products are dropped) | NOAA HMS daily shapefiles; **AirNow public file archive** `files.airnowtech.org/airnow/2026/<YYYYMMDD>/daily_data_v2.dat` (keyless — resolves the historical-AirNow gap below); IEM NWS VTEC archive (EH/XH/HT) | 8 across the corridor; 1/2/4 where heat co-occurs |

Known gaps:
- NWS Air Quality Alerts are non-VTEC products and are not in the IEM VTEC archive, so
  `smoke_nyc_2023` has no NWS alerts; the live NWS provider does ingest them.
- AirNow observations come from the keyless public file archive (`files.airnowtech.org`,
  daily site AQI) — used by `smoke_canada_2026`; the key-gated API is only needed live.
  `smoke_nyc_2023` predates that route in this repo and still has no AirNow rows.
- Outage percent uses the Moehl modeled county customers; where a county reports more
  customers out than that total (a documented EAGLE-I data-quality issue) the percent is
  clamped at 100 with the raw value kept in `metrics.outage_pct_raw`.
- IEM's `watchwarn.py` ignored the `phenomena` filter in our pulls, so the raw CSVs contain
  more products than used; `parse_iem_csv` keeps only the products the cards trigger on.
- Polygon → county coverage (HMS, dated zones) is approximate: a county counts when its
  representative point is inside the polygon or a polygon vertex is inside the county.
