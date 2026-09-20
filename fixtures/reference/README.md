# Cached reference data

Rebuildable with `make reference`. Raw pulls live under `raw/`; derived files are what the
loaders read. Every file records its source and retrieval date.

| File | Built by | Source | Status |
| --- | --- | --- | --- |
| `counties.geojson` | `scripts/build_county_boundaries.py` | Census cartographic boundary shapefile, counties, **1:5m**, vintage 2023 (`cb_2023_us_county_5m.zip`, retrieved 2026-09-20; raw zip in `raw/`). 3,235 counties incl. PR, GU, AS, MP, VI. The 1:20m file omits the Pacific/Caribbean territories. | built |
| `nws_zone_county.csv` | `scripts/build_nws_zones.py` | NWS zone-county correlation file `bp16ap26.dbx` (https://www.weather.gov/gis/ZoneCounty, retrieved 2026-09-20; raw copy in `raw/`). Maps public forecast zones (UGC `SSZnnn`) to county FIPS for the current zone numbering. | built |
| `zip_county.csv` | `scripts/build_zip_county.py` | Census 2020 ZCTA↔county relationship file (`tab20_zcta520_county20_natl.txt`, retrieved 2026-09-20; raw copy in `raw/`). Dominant county by land-area share of each ZCTA part. HUD USPS ZIP-county crosswalk (address shares) is used instead when `HUD_API_TOKEN` is set. | built |
| `facilities.geojson` | `scripts/build_facilities.py` | VA Lighthouse Facilities API **v1**, `GET /facilities?type=health` paged as JSON:API (`apikey` header). Pulled 2026-09-20 from **sandbox-api.va.gov** (self-service keys are sandbox-only; production returns 401 until access is granted; same dataset): 1,400 health facilities in 3 pages, raw pages in `raw/`. | built |
| `county_visn.csv` | — | Not built. data.va.gov `9hbf-9jzg` ("VISN, Markets, Submarkets, Sectors and Counties") is a non-tabular 377 MB FY2017 blob whose download endpoint returns "Unable to find blob" (checked 2026-09-20); no tabular VISN/market/county dataset was found via the Socrata catalog. VISN attribution therefore uses each facility's own `visn` attribute from the Facilities API. Market is unattributed. | not available |
| `places_county.csv` | `scripts/build_places.py` | CDC PLACES County Data (GIS Friendly), **2025 release** (`i46a-9kgh`, data.cdc.gov Socrata, retrieved 2026-09-20; raw JSON in `raw/`). Crude prevalence % for adults 18+ (general population): COPD, current asthma, CHD, diabetes, depression, frequent mental distress, high BP, obesity, stroke, disability. PLACES no longer publishes a CKD measure. 187 counties have suppressed values (blank). | built |
| `vetpop_county.csv` | `scripts/build_vetpop.py` | VA NCVAS **VetPop2023**, Table 9L county-level living veterans (all ages/sexes), 9/30 projections 2023–2030 (workbook `9L_VetPop2023_County_NCVAS.xlsx`, retrieved 2026-09-20; git-ignored under `raw/`, re-downloaded when missing). Territories are single rows (Puerto Rico 72000, Guam 90066, …) and are spread evenly over their counties at load; "Foreign Countries" (99000, ~77k) is excluded. | built |

**Facility → county attribution** (`xevents.geography.attribute_facilities`): point-in-polygon
of the facility coordinates against `counties.geojson` first; ZIP → county crosswalk as
fallback; `county_source` on every facility records which. On the 2026-09-20 pull: 1,399 by
point-in-polygon, 0 by ZIP, 1 unresolved (`vha_358` Manila VA Clinic, Philippines — no US
county; excluded from event matching). ZIP-only attribution would have missed 22, including
seven VAMCs with institutional "unique" ZIPs (e.g. Pittsburgh 15240, Richmond 23249) that are
not ZCTAs.

**Catchments and panels (M3).** Each county is assigned to its nearest anchor *station*
(VAMC/HCC, great-circle distance to the county's representative point; profile
`catchment.anchor_classifications`); clinics report their station's panel (matched by health
care system, else nearest). Panels = scoped population × rate: VA-literature rates apply to
`vha_users` = veterans × 0.50 (profile `scopes`), PLACES rates apply to all veterans, national
counts (dialysis) are allocated by veteran share. Every estimate carries formula, inputs,
sources and caveats. On the 2026-09-20 data: 3,235 counties → 183 of 184 stations
(Northport VAMC, NY receives none: Long Island's counties resolve to neighbouring stations).

Caveats to surface in the UI's provenance popover:
- ZCTAs approximate USPS ZIP codes; ~30% of ZCTAs span more than one county and are assigned
  to the county holding the largest land-area share (`share` column < 1.0 flags them).
- County boundaries are 1:5m generalized; a facility within a few hundred metres of a county
  line could be attributed to the neighbour.
