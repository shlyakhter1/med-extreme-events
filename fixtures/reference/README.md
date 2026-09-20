# Cached reference data

Rebuildable with `make reference`. Raw pulls live under `raw/`; derived files are what the
loaders read. Every file records its source and retrieval date.

| File | Built by | Source | Status |
| --- | --- | --- | --- |
| `counties.geojson` | `scripts/build_county_boundaries.py` | Census cartographic boundary shapefile, counties, **1:5m**, vintage 2023 (`cb_2023_us_county_5m.zip`, retrieved 2026-09-20; raw zip in `raw/`). 3,235 counties incl. PR, GU, AS, MP, VI. The 1:20m file omits the Pacific/Caribbean territories. | built |
| `zip_county.csv` | `scripts/build_zip_county.py` | Census 2020 ZCTA↔county relationship file (`tab20_zcta520_county20_natl.txt`, retrieved 2026-09-20; raw copy in `raw/`). Dominant county by land-area share of each ZCTA part. HUD USPS ZIP-county crosswalk (address shares) is used instead when `HUD_API_TOKEN` is set. | built |
| `facilities.geojson` | `scripts/build_facilities.py` | VA Lighthouse Facilities API **v1**, `GET /facilities?type=health` paged as JSON:API (`apikey` header). Pulled 2026-09-20 from **sandbox-api.va.gov** (self-service keys are sandbox-only; production returns 401 until access is granted; same dataset): 1,400 health facilities in 3 pages, raw pages in `raw/`. | built |
| `county_visn.csv` | — | Not built. data.va.gov `9hbf-9jzg` ("VISN, Markets, Submarkets, Sectors and Counties") is a non-tabular 377 MB FY2017 blob whose download endpoint returns "Unable to find blob" (checked 2026-09-20); no tabular VISN/market/county dataset was found via the Socrata catalog. VISN attribution therefore uses each facility's own `visn` attribute from the Facilities API. Market is unattributed. | not available |
| `places.csv`, `vetpop.csv` | M3 | CDC PLACES county measures; VetPop county veteran counts. | M3 |

**Facility → county attribution** (`xevents.geography.attribute_facilities`): point-in-polygon
of the facility coordinates against `counties.geojson` first; ZIP → county crosswalk as
fallback; `county_source` on every facility records which. On the 2026-09-20 pull: 1,399 by
point-in-polygon, 0 by ZIP, 1 unresolved (`vha_358` Manila VA Clinic, Philippines — no US
county; excluded from event matching). ZIP-only attribution would have missed 22, including
seven VAMCs with institutional "unique" ZIPs (e.g. Pittsburgh 15240, Richmond 23249) that are
not ZCTAs.

Caveats to surface in the UI's provenance popover:
- ZCTAs approximate USPS ZIP codes; ~30% of ZCTAs span more than one county and are assigned
  to the county holding the largest land-area share (`share` column < 1.0 flags them).
- County boundaries are 1:5m generalized; a facility within a few hundred metres of a county
  line could be attributed to the neighbour.
