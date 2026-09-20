# Replay scenarios

Each `<scenario>/` holds raw archived source files (`raw/`), a `build.py` that turns them
into `events.json` (normalized `Event` records, the same model the live providers produce),
and the provenance below. Rebuild all with `make scenarios`; load with
`EVENT_MODE=replay make ingest` (each scenario's rows are replaced, keyed by `scenario`).

| Scenario | Window | Events | Sources (retrieved 2026-09-20) | Expected cards |
| --- | --- | --- | --- | --- |
| `heat_dome_2021` | 2021-06-25 → 07-08 | 20 NWS (8 Excessive Heat Warning, 8 Excessive Heat Watch, 4 Heat Advisory), 129 counties in WA/OR/ID | IEM NWS VTEC archive CSV (EH/HT, W/Y/A); IEM zone geometries valid 2021-06-27 for OR/WA/ID (2021 zone numbering predates the 2024–26 renumbering, so zone→county comes from dated geometry) | 1, 2, 4 for WA/OR facilities |
| `ian_2022` | 2022-09-23 → 11-04 | 66 NWS (hurricane/tropical storm/storm surge/flood watches & warnings) + 1 OpenFEMA DR-4673 (67 counties), 70 counties in FL | IEM NWS VTEC archive CSV (HU/TR/SS/FF/FA, W/A); IEM FL zone geometries valid 2022-09-27; OpenFEMA DisasterDeclarationsSummaries | 3, 5, 6 for FL facilities; dialysis first |
| `smoke_nyc_2023` | 2023-06-06 → 06-09 | 9 HMS smoke events (3 days × Light/Medium/Heavy); heavy smoke over NYC on June 7 | NOAA HMS daily smoke polygon shapefiles | none in v1 (bonus; exercises the smoke provider) |

Known gaps:
- NWS Air Quality Alerts are non-VTEC products and are not in the IEM VTEC archive, so
  `smoke_nyc_2023` has no NWS alerts; the live NWS provider does ingest them.
- No AirNow observations in any scenario: historical pulls need `AIRNOW_API_KEY`.
- IEM's `watchwarn.py` ignored the `phenomena` filter in our pulls, so the raw CSVs contain
  more products than used; `parse_iem_csv` keeps only the products the cards trigger on.
- Polygon → county coverage (HMS, dated zones) is approximate: a county counts when its
  representative point is inside the polygon or a polygon vertex is inside the county.
