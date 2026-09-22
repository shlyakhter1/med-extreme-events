# Data sources

*Part of the [design and user guide](README.md). As of 2026-09-21. Retrieval dates are
those of the cached copies in `fixtures/`.*

Every source is public. Nothing about an individual patient is used, and no source needs a
key at demo time: the reference tables and replay scenarios are cached in `fixtures/` with
their raw files and a builder script, so the demo runs offline. Keys and network access are
needed only to **rebuild** the caches (`make reference`, `make scenarios`) or to run
**live** mode.

## Summary

| Source | Provides | Layer | Used | Auth | Cached as |
| --- | --- | --- | --- | --- | --- |
| [NWS alerts API](#nws-alerts-apiweathergov) | Watches, warnings and advisories in force now (CAP) | Event | live | User-Agent | `fixtures/live/raw/` |
| [IEM VTEC archive](#iowa-environmental-mesonet-iem) | Historical NWS products, plus dated zone geometry | Event | replay builds, live 2-week backfill | none | `fixtures/events/*/raw/` |
| [NWS zone-county correlation](#nws-zone-county-correlation-file) | Forecast zone → county | Event | all NWS resolution | none | `fixtures/reference/nws_zone_county.csv` |
| [NOAA HMS smoke](#noaa-hms-smoke-polygons) | Daily smoke plume polygons by density | Event | live, `smoke_nyc_2023`, `smoke_canada_2026` | none | `fixtures/events/smoke_*/raw/` |
| [OpenFEMA](#openfema-disaster-declarations) | Disaster declarations by county | Event (context) | live, `ian_2022` | none | `fixtures/events/ian_2022/raw/` |
| [AirNow](#airnow) | Monitor AQI observations | Event | live (API key); `smoke_canada_2026` via the keyless file archive | API key (live only) | `fixtures/live/raw/`, `fixtures/events/smoke_canada_2026/raw/` |
| [Census county boundaries](#census-county-boundaries) | County polygons, the join geometry and basemap | Shared | always | none | `fixtures/reference/counties.geojson` |
| [VA Facilities API](#va-lighthouse-facilities-api) | 1,400 VA health facilities, location, VISN, status | Medical | reference build | API key | `fixtures/reference/facilities.geojson` |
| [Census ZCTA ↔ county / HUD USPS](#zip--county-census-zcta-or-hud-usps) | ZIP → county fallback for facilities | Medical | reference build | HUD token optional | `fixtures/reference/zip_county.csv` |
| [VA VetPop2023](#va-vetpop2023) | Living veterans per county, 2023–2030 | Medical | panel sizing | none | `fixtures/reference/vetpop_county.csv` |
| [CDC PLACES](#cdc-places) | County chronic-disease prevalence | Medical | panel sizing | none | `fixtures/reference/places_county.csv` |
| [Card literature](#clinical-literature-cards) | Evidence, rates and guidance behind each card | Medical | card content, profile rates | n/a | `cards/*.yaml`, `profiles/va.yaml` |
| [Carbon LCA literature](#medication-carbon-estimates) | Medication life-cycle carbon | Medical (display) | carbon panel | n/a | `docs/carbon.yaml` |

## Event layer sources

### NWS alerts (`api.weather.gov`)

- **Endpoint:** `GET https://api.weather.gov/alerts/active?status=actual`, returned as CAP
  GeoJSON features.
- **Auth and etiquette:** no key, but a `User-Agent` with contact details is mandatory
  (`NWS_USER_AGENT`). Poll no more often than every 30 seconds. The system polls every
  15–30 minutes.
- **Used for:** heat, tropical, surge, flood and Air Quality Alert products (the vocabulary
  in `NWS_EVENT_TYPES`). CAP `SAME` codes give county FIPS directly. UGC zones resolve
  through the correlation file.
- **Code:** `src/xevents/providers/nws.py`.
- **Limits:** it reports only what is in force *now* and keeps no history, which is why the
  IEM archive exists in this system. The 2025 NWS rename (Excessive Heat → Extreme Heat) is
  handled by listing both names in the card triggers.

### Iowa Environmental Mesonet (IEM)

- **Endpoints:** `https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py?accept=csv`
  (the VTEC watch/warning archive), and `…/api/1/nws/ugcs.geojson?valid=<date>` (zone
  geometry as it was on a given date).
- **Used for:** all historical NWS products in the replay scenarios, and the 14-day live
  backfill. Rows are grouped by VTEC event identity, using the earliest issue time and the
  latest expiry. Dated zone geometry is intersected with county polygons, because NWS
  renumbered WA/OR/ID zones after 2021 and the current correlation file lacks the old codes.
- **Code:** `src/xevents/providers/iem_archive.py`, `fixtures/events/*/build.py`.
- **Limits:** non-VTEC products (such as Air Quality Alerts) are absent. The `phenomena`
  filter was ignored in our pulls, so the parser keeps only the products that cards trigger
  on.

### NWS zone-county correlation file

- **Source:** <https://www.weather.gov/gis/ZoneCounty>, file `bp16ap26.dbx` (retrieved
  2026-09-20), which has 4,848 rows.
- **Used for:** mapping public forecast zones (`SSZnnn`) to county FIPS.
- **Builder:** `scripts/build_nws_zones.py`. **Code:** `src/xevents/geography/nws_zones.py`.
- **Connecticut:** NWS still uses the legacy counties, while every other source uses the 2022
  planning regions. `fixtures/reference/ct_legacy_county_crosswalk.csv`, built by
  `scripts/build_ct_crosswalk.py` using grid-sampled area shares, bridges the two.

### NOAA HMS smoke polygons

- **Source:** `https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/YYYY/MM/hms_smokeYYYYMMDD.zip`.
  A daily shapefile, finalized the next morning, with fields for satellite, start, end and
  density (Light, Medium or Heavy).
- **Used for:** wildfire-smoke events. There is one event per day per density, and
  counties come from approximate polygon coverage.
- **Code:** `src/xevents/providers/hms.py`, `src/xevents/geography/polygons.py`.
- **Limits:** these are analyst-drawn plumes of smoke in the atmospheric column, seen
  from satellite. They do not measure surface air quality. Coverage is approximate at plume
  edges. Card 8 fires on Medium and Heavy density.

### OpenFEMA disaster declarations

- **Source:** `https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries`, no auth.
  It has one row per (disaster, designated area).
- **Used for:** **context only**. Declarations are post-hoc, so no card triggers on them.
  They are grouped per disaster, typed by incident, and carry the disaster number in
  `metrics`.
- **Code:** `src/xevents/providers/openfema.py`.

### AirNow

- **Endpoint:** `https://www.airnowapi.org/aq/data/` ("Observations by Monitoring Site",
  by bounding box). It is in AirNow's retained 2026 service list. The ZIP and lat/long
  observation services that retire on 2026-09-30 are not used.
- **Auth:** a free key (`AIRNOW_API_KEY`), sent as a query parameter. The limit is 500
  requests per hour, so the provider fetches one bounding box per call and caches every
  response.
- **Used for:** air-pollution events. Monitors are mapped to counties by point-in-polygon.
  Live mode only, and skipped when there is no key.
- **Historical route (no key):** the AirNow public file archive
  `https://files.airnowtech.org/airnow/<yyyy>/<yyyymmdd>/daily_data_v2.dat` gives one daily
  AQI per site and parameter (PM2.5 24-h, ozone 8-h) with coordinates;
  `parse_daily_data_v2` maps it onto the same observation rows, so replay fixtures
  (`smoke_canada_2026`) carry AirNow events without a key.
- **Code:** `src/xevents/providers/airnow.py`.
- **Limits:** the **response shape has not been verified against a real key**. Check the
  first live pull in `fixtures/live/raw/airnow_data_*.json`. None of the scenarios contain
  AirNow data.

### EAGLE-I county power outages (`providers/eagle_i.py`)

- **What:** customers without power per county, collected by ORNL's EAGLE-I program for DOE
  from utilities' public outage maps. Live: an ArcGIS FeatureServer table carrying the
  EAGLE-I API fields (`currentOutage`, `currentOutageRunStartTime`, `countyFIPSCode`,
  `coveredCustomers`, `modelCount` …), polled hourly; FEMA's partner service
  (`gis.fema.gov/arcgis/rest/services/Partner/PowerOutages_EAGLE_I`) is the default but
  answered *Token Required* on 2026-09-21, so set `EAGLEI_TOKEN`, or point
  `EAGLEI_FEATURE_URL` at a public mirror with the same fields (state emergency-management
  agencies publish them). Replay: the ORNL yearly county CSVs (15-minute cadence,
  2014–2025, figshare doi:10.6084/m9.figshare.24237376), sliced per scenario and resampled
  to hourly maxima.
- **Denominator:** `fixtures/reference/eaglei_customers.csv` (Moehl et al. modeled county
  customers, 2022), so live and replay compute `outage_pct` the same way; the feed's own
  coverage fields are kept in `metrics` as `feed_*` for cross-checks.
- **Events:** one observed `power_outage` per (county, poll) at or above the lowest
  `outage_pct_min` any card asks for (10 %). Consecutive polls are contiguous events, which
  is what the engine's `sustained_polls_min` debounce counts.
- **Honest display:** every render carries the required attribution *"Electric customer
  outage data provided by EAGLE-I, Department of Energy."*, states that customers are
  meters/accounts rather than people, and that ~8 % of US customers (small rural and
  municipal utilities) are not covered. The live feed appears in the freshness banner like
  every other source.

### HHS emPOWER electricity-dependent DME (reference layer, `denominators.py`)

- **What:** the HHS emPOWER public REST service's de-identified monthly counts of Medicare
  (FFS + Advantage) beneficiaries who rely on electricity-dependent durable medical
  equipment, by county and ZIP, cached as `fixtures/reference/empower_county.csv` and
  `empower_zip.csv` by `scripts/build_empower.py` (vintage in the file header; manual,
  monthly refresh; layer ids and field names pinned so a portal change fails the build).
- **How it is used:** a *measured exposure layer* beside the condition-based veteran
  estimate, never instead of it. `PanelEstimator.empower_dme` sums the county counts over a
  station's catchment (unit: Medicare beneficiaries). Card 6's `electricity_dependent_dme`
  sub-panel reports it; outage-triggered items carry it as `exposure` and show both numbers;
  for outage events the within-acuity ranking multiplier is `outage_pct × empower_dme`
  (measured × measured) with the formula in the provenance popover.
- **Limits:** a Medicare proxy, not veteran-specific (every render says so); small cells
  (1–10) are masked to 11, so small counties read high; the planning/outreach datasets
  beyond the public layer are restricted to public-health officials.

### Not yet connected

`requirements.md` §4 names one more event source that has no provider yet: **NWS HeatRisk**
(a gridded 7-day heat-risk raster, needed by the `heatrisk_min` triggers).

## Shared reference

### Census county boundaries

- **Source:** Census cartographic boundary file, counties at **1:5m**, vintage 2023
  (`cb_2023_us_county_5m.zip`, retrieved 2026-09-20). It contains 3,235 counties,
  including PR, GU, AS, MP and VI. The 1:20m file omits the territories.
- **Used for:** every county join (facility point-in-polygon, polygon coverage, catchment
  representative points), and the map basemap served at `/reference/counties`. There are no
  third-party tiles.
- **Builder:** `scripts/build_county_boundaries.py`. **Code:** `src/xevents/geography/counties.py`.
- **Limits:** generalized boundaries, so a facility within a few hundred metres of a county
  line can be attributed to the neighbouring county.

## Medical layer sources

### VA Lighthouse Facilities API

- **Endpoint:** `GET https://api.va.gov/services/va_facilities/v1/facilities?type=health&page=&per_page=`,
  returned as JSON:API. The key goes in the `apikey` header (`VA_FACILITIES_API_KEY`, free at
  developer.va.gov). **Use v1 only.** v0 and its `/facilities/all` GeoJSON endpoint are gone,
  so the builder constructs GeoJSON itself.
- **Pulled:** 2026-09-20 from `sandbox-api.va.gov` (self-service keys are sandbox-only and
  production returns 401; the builder falls back automatically). This gave 1,400 health
  facilities in 3 pages, with the raw pages kept in `fixtures/reference/raw/`.
- **Used for:** the facility spine: location, classification (station vs clinic), VISN,
  health care system and operating status.
- **Builder:** `scripts/build_facilities.py`. **Code:** `src/xevents/providers/va_facilities.py`.
- **Limits:** there is no VA market attribution. The data.va.gov VISN/market/county dataset
  (`9hbf-9jzg`) is a broken FY2017 blob, and no tabular substitute was found.

### ZIP → county (Census ZCTA or HUD USPS)

- **Default source:** Census 2020 ZCTA↔county relationship file
  (`tab20_zcta520_county20_natl.txt`). Each ZCTA is assigned to the county with the largest
  land-area share, for 33,791 ZIPs in total.
- **Optional:** HUD USPS ZIP-county crosswalk (address shares), used when `HUD_API_TOKEN` is
  set.
- **Used for:** a fallback when point-in-polygon fails for a facility. On the current pull
  it is used for 0 facilities.
- **Builder:** `scripts/build_zip_county.py`. **Code:** `src/xevents/geography/zip_county.py`.
- **Limits:** ZCTAs only approximate USPS ZIPs. About 30 % span more than one county, and
  institutional ZIPs are not ZCTAs.

### VA VetPop2023

- **Source:** VA NCVAS VetPop2023 Table 9L, county-level living veterans, projections as of
  9/30 for 2023–2030 (`9L_VetPop2023_County_NCVAS.xlsx`, from va.gov/vetdata). The workbook
  is gitignored and re-downloaded when missing.
- **Used for:** veterans per county, and so the size of every catchment. The profile's
  `projection_year` is 2026. The national total is checked against 17,260,286 (±5 %).
- **Builder:** `scripts/build_vetpop.py`. **Code:** `ReferenceTables` in `src/xevents/denominators.py`.
- **Limits:** territories are single rows, spread evenly over their counties. "Foreign
  Countries" (~77k) is excluded.

### CDC PLACES

- **Source:** CDC PLACES County Data (GIS Friendly), 2025 release, Socrata dataset
  `i46a-9kgh` on data.cdc.gov. It gives crude prevalence for adults 18+ in the general
  population.
- **Measures kept:** COPD, current asthma, CHD, diabetes, depression, frequent mental
  distress, high blood pressure, obesity, stroke and disability. There is no CKD measure,
  because PLACES dropped it.
- **Used for:** panel keys that the profile maps to a `places_measure`, applied to all
  veterans in each county, and as a cross-check for the VA diabetes multiplier. None of the
  cards 1–6 sizes its panel on PLACES directly; Cards 7 and 8 do.
- **Builder:** `scripts/build_places.py`.
- **Limits:** these are model-based estimates for the general population, not veterans. The
  UI says so. 187 counties have suppressed values.

### Clinical literature (cards)

Each card cites its evidence in `sources`, and each claim in `evidence.claims` carries a tier
(`strong`, `inferential` or `expert_guidance`). The profile's condition rates (bipolar 3.0 %,
schizophrenia 3.6 %, heart failure 5 %, diabetes 25 % of VHA users, and 52,000 veterans on
dialysis) come from the same literature, via `docs/card-library.md`. Guidance sources
include FDA insulin-storage guidance, CDC heat-and-medications guidance, and KCER/ESRD
network materials. The library's own reference list is authoritative.

### Medication carbon estimates

`docs/carbon.yaml` compiles published pharmaceutical life-cycle assessments and analogues.
`docs/carbon-footprint.md` lists the methods and references. These figures are for display
only, with ranges and confidence levels.

## Rebuilding and adding sources

- `make reference` rebuilds the reference tables. It needs network access, and the
  facilities step needs `VA_FACILITIES_API_KEY`. `make scenarios` rebuilds the replays from
  their raw files.
- To add a source, write a provider (event layer) or a builder (reference data) that caches
  raw responses under `fixtures/`, then add a row to `fixtures/reference/README.md` or the
  scenario README with the URL and retrieval date. The providers are the only network code.
- **Agent Skills** for these sources live in the sibling repository `nyc2026-dataset` and are
  used in place: `search-va-facilities-api`, `search-epa-airnow-aqs`,
  `search-noaa-ncei-daily-summaries`, `search-cdc-places`,
  `search-cdc-heat-medications-guidance`, and others. See "Data-source skills" in
  `CLAUDE.md`. A skill's verified URLs take precedence over this document. Record any
  disagreement in `PROGRESS.md`.
