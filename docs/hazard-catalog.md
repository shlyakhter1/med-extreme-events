# US Hazard Event & Source Catalog

*As of 2026-09-21. The system's map of hazard types → data sources for the US, with access details, temporality mapping, and card relevance. Machine-readable mirror: `data/hazard_sources.yaml`. Status: `integrated` (in the demo), `this_iteration` (M6–M10), `backlog` (cataloged for later). Global sources listed at the end.*

## Integrated / this iteration

| Hazard | Source | Access | Granularity / cadence | Temporality | Cards | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Heat (advisory/warning) | NWS api.weather.gov /alerts | Free, User-Agent header | NWS zone + county; alerts as issued | watch→forecast, warning/advisory→imminent | 1, 2, 4 | integrated |
| Heat (sub-advisory) | NWS HeatRisk (experimental) | GeoTIFF/KML + ArcGIS ImageServer | Gridded, daily, 7-day | forecast | 1, 2, 4 | backlog (stub) |
| Hurricane / tropical / flood | NWS alerts + NHC products | Free | Zone/county | watch→forecast, warning→imminent | 3, 5, 6 | integrated |
| Disaster declarations | OpenFEMA DisasterDeclarationsSummaries v2 | Free, no key, OData filters | County | observed | context | integrated |
| Air pollution (AQI) | AirNow API (2026 consolidated endpoints) | Free key; 500 req/h | ZIP / lat-lon; hourly obs, daily forecast | obs→observed, forecast→forecast | 8 | integrated |
| Wildfire smoke | NOAA HMS smoke polygons | Free; shapefile/KML/WFS, daily | Polygon → county intersect | observed | 8 | integrated |
| **Extreme cold / winter / ice** | NWS alerts (post-SCN23-44 taxonomy; legacy names normalized) | Free | Zone/county | watch→forecast, warning/advisory→imminent | **7** | this_iteration |
| **Power outage (occurring)** | **EAGLE-I via FEMA ArcGIS FeatureServer**; ORNL historical county CSVs 2014–2025 for replay | Free, no key; hourly (live), 15-min (historical). Attribution required: "Electric customer outage data provided by EAGLE-I, Department of Energy." | County FIPS; customers-out (meters, not people; ~8% of customers uncovered) | observed | 3, 5, 6 (+boost to heat/cold cards) | this_iteration |
| **Electricity-dependent exposure** | HHS emPOWER public REST (ArcGIS) | Free; monthly vintage | ZIP + county DME beneficiary counts (Medicare proxy) | n/a (exposure layer, cached reference) | 6 sub-panel; outage ranking | this_iteration |

## Backlog — health-relevant, sources verified

| Hazard | Source | Access | Granularity / cadence | Temporality | Plausible card | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Power outage (planned) | PG&E/SCE/SDG&E PSPS portals; CPUC rollup | Machine-readable feeds partner-gated; rollup open but lagged | Circuit/county; 1–2 day notice | forecast | 5, 6 pre-event | Apply for partner access if CA in scope |
| Earthquake | USGS GeoJSON feeds + FDSN query; PAGER alert levels | Free, keyless, real-time | Point + shaking extent; minutes | observed | Earthquake × dialysis/DME infrastructure | Highest-value backlog provider; PAGER Orange/Red trigger |
| Flood (observed/forecast stage) | NOAA NWPS API + Flood Inundation Mapping (ArcGIS) | Free; "not supported 24/7, may change without notice" | Gauge + inundation polygons; NWM forecast | obs + forecast | Complements 3/5/6 flood triggers | FIM coverage expanding toward national by late 2026 |
| Wildfire incidents/perimeters | NIFC/WFIGS ArcGIS FeatureServers (IRWIN-sourced) | Free with attribution | Perimeter polygons, 5-min | observed | Sharpens 8; evacuation context | |
| Drought / water access | US Drought Monitor REST (usdmdataservices.unl.edu); CDC Tracking API | Free | County/HUC, weekly | observed | Private-well/water-access card | |
| High wind / tornado / derecho | NWS alerts (existing provider; taxonomy extension only) | Free | Zone/county | forecast/imminent | Outage proxy; DME pre-positioning | Cheap add when needed |
| Extreme-heat + power grid stress | EIA-930 hourly demand/forecast by BA | Free key | Balancing authority, hourly | forecast (day-ahead) | Indirect outage-risk signal | Proxy only; never a customers-out substitute |
| UV / other environmental | EPA UV index; CDC Environmental Tracking APIs | Free | ZIP/county | forecast | Low priority | |
| Major-outage incident record | DOE OE-417 filings + ORNL annual summaries | Free | Event-level, 6–72 h lag | observed | Backtest cross-check | Not a live trigger |

## Global sources (for expansion beyond US)

| Need | Best source (2026) | Access | Notes |
| --- | --- | --- | --- |
| Real-time global alerting | GDACS (EC-JRC) | Free GeoJSON API, MIT license | EQ, TC, flood, volcano, drought, wildfire; Green/Orange/Red |
| Historical tropical cyclones | IBTrACS (NOAA NCEI) | Free; updated ~3×/week | 1840s–present, 3-hourly; replay/backtest catalog |
| Impact/severity catalog | EM-DAT (CRED/UCLouvain) | Registration; non-commercial; no real-time API | 27,000+ disasters since 1900; severity thresholds for backtesting |
| Meta-aggregation | NASA EONET v3 | Free API | Convenient prototype layer (wraps GDACS, NHC, InciWeb, etc.) |
| Humanitarian context / mapping | ReliefWeb API; Copernicus EMS; USGS PAGER | Free | Situation reports, activation mapping, casualty-scale alerts |

## Licensing & fragility flags
- **PowerOutage.us: do not integrate.** Contact-sales pricing; Aug-2025 API terms prohibit scraping and any AI/ML/RAG use — a licensing landmine for this system.
- Direct utility/Kubra map scraping is fragile (per-deployment GUIDs, silent breakage) and redundant — EAGLE-I already aggregates it.
- EM-DAT is non-commercial; EONET inherits upstream stability; NWPS API explicitly unsupported-24/7.
- AirNow legacy endpoints retired Sep 30, 2026 — consolidated endpoints only.
- emPOWER planning/outreach datasets (beyond the public REST layer) are restricted to public-health officials.
