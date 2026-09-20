# PROGRESS

Short dated entries, newest first. One milestone per session (M0 → M5).

## 2026-09-20 — demo feedback round: run/host docs, event exploration, timeline, key-free map

Four issues raised after walking through M5, all fixed and covered by tests.

- **"bad timestamp" on every page.** The header form submitted `+00:00`, and `+` is the URL
  encoding for a space, so the app rejected the as-of value it had just rendered. The control
  is now `<input type="datetime-local">` (no offset, so no `+`), and `timeparse.parse_at`
  accepts the space-for-plus form, a trailing `Z`, minute precision and a bare date. Naive
  values are read as UTC. Regression test covers all five spellings.
- **Events were not explorable.** New `/dashboard/events` (window, severity, county and
  facility counts, active-vs-all toggle) and `/dashboard/events/{key}` (counties on a map,
  UGC codes, CAP metrics, raw payload path, the action items it produced). The dashboard
  gained an active-events table, and both banners now state that times are UTC and whether
  the feed is live or replayed. API gained `GET /events/detail?key=`.
- **Playback had no timeline and pause did not hold.** Rewritten: an SVG timeline with one
  lane per event type, a bar per event across its active window, day gridlines, a playhead,
  click/drag to seek and click-a-bar to inspect. Transport uses an explicit `playing` flag
  with step buttons, spacebar and arrow keys. The old version refetched facility detail on
  every tick, which is what made it look like it resumed on its own; nothing fetches during
  playback now and county/facility repaints are diffed.
- **Map demanded an API key.** Both maps used CARTO raster tiles, which watermark
  unregistered use. `web/static/map.js` now draws the county polygons the app already serves
  at `/reference/counties`. No third-party tile request, no key, works offline.

**Packaging and hosting** (the other half of the feedback): `requirements.txt` generated from
the lockfile with pinned hashes for pip users; `Dockerfile` that bakes the demo database at
build time (verified: 381 MB image, serves every page with no key, no database server and no
network); `fly.toml`; `docs/deploy.md` covering local, container, Fly/Render/Cloud Run, live
mode with a writable volume and a refresh schedule; README rewritten to lead with how to run
it. `make lint test`: 107 passed.

**Incident note.** The first Docker build filled the host disk, which wedged the Docker
daemon (a stale `com.docker.backend` from Sep 10 survived restarts and had to be killed).
Pruning images and build cache reclaimed 55 GB inside Docker; its virtual disk shrank from
83 GB to 1.5 GB and the host went from 5.7 GB to 87 GB free.

## 2026-09-20 — M5: API + UI (done)

**Done.**
- Server-rendered pages (Jinja2 + htmx, `src/xevents/web/views.py` + `templates/`):
  - `/` **dashboard**: header with scenario switcher (three replays + **live (now)**) and an
    "as of" time; replay defaults to the scenario's peak hour (`/scenarios` → `peak_at`);
    event board ranked by acuity, then severity × panel (stations before clinics on ties);
    outreach queue count for unacknowledged high-acuity items; Leaflet map of facilities
    colored by active event and sized by panel; live mode shows a **feed-freshness banner**
    (`/feeds`: per-source count, last ingest, stale > 6 h) and never renders an empty board
    as an all-clear.
  - `/dashboard/facilities/{id}` **drill-down**: fired cards (strongest event per role),
    clinician checklist grouped pre-event / during, panel with expandable "how was this
    number computed?" (formula, components, caveats, sources), role toggle via htmx
    (care team / patient / caregiver), event id + card version + evidence tier + citations
    on every card, **Acknowledge / Mark completed** buttons posting to the status machine.
  - `/demo/patient-view?facility=&card=&role=` read-only patient/caregiver rendering of the
    same action items (verbatim card text, safety line, escalation triggers, disclaimer).
- `make demo`: fresh SQLite DB → reference + catchments → three replays → action items →
  serves the dashboard and opens it (no network needed; ~1 minute).
- Live mode verified end to end on the Postgres DB: `EVENT_MODE=live make ingest match`
  ingested real NWS/OpenFEMA/HMS events and the dashboard rendered them with the banner.
- `make lint test`: green.

**Success criteria (docs/implementation-plan.md §1), as verified through the pages.**
1. Heat dome replay: Cards 1/2/4 for WA/OR facilities with sized panels and clinician +
   patient content — dashboard at the peak hour lists 68 facilities / 708 open items;
   Portland VAMC page shows all three cards. ✔
2. Ian replay: Cards 3/5/6 for Florida; dialysis ranked first (acuity rank 0). ✔
3. `EVENT_MODE=live` ingests real feeds with no code change and the live dashboard renders
   whatever is active, with freshness. ✔ (AirNow still needs a key.)
4. Traceability: every panel number expands to its formula/inputs/sources; every card shows
   its event id, card id + version, evidence tier and citations. ✔
5. `make demo` rebuilds from empty in one command. ✔

**Not done / next.** Notification channel adapters remain stubs (out of scope). Caregiver
content is empty pending reviewed text. AirNow response shape unverified without a key.
Recorded run-through of the demo script is the user's to do.

## 2026-09-20 — M4: matching engine + action-item store (done) + playback view

**Done.**
- `engine.py`: pure `match(events, cards, facilities, profile, panels, now)` → one
  `ActionItem` per (event, card, facility, role), acuity-ranked; every trigger evaluation is
  logged (event, card, matched / why not). Facilities in scope = facility county ∈ event
  counties; triggers = card `event_triggers` (NWS product names, HeatRisk, AQI, FEMA,
  outage). Within (card, facility, role, event type) the strongest overlapping event wins
  and weaker items are marked `superseded_by` it.
- `ActionItem` model per requirements §7 with card content copied verbatim (actions,
  patient message, escalation with the profile's templated default response, safety line,
  evidence tier, sources, panel estimate, window = onset − card.window_days.max → expires).
- Store: `action_items` table; upsert by natural key keeps delivery/acknowledgement
  progress and `created_at`, applies/lifts supersession; status machine
  issued→delivered→acknowledged→completed|expired|superseded (`transition_action_item`,
  `expire_action_items`). `make match` (replay: all scenarios; live: now + auto-expire).
- Golden tests (`tests/test_golden.py`, `tests/golden/*.json`): heat dome 2021 → 1,608
  items (720 issued, 888 superseded) across 70 WA/OR/ID facilities, Cards 1/2/4 only,
  Portland + Seattle + American Lake included; Ian 2022 → 3,122 items across 81 FL
  facilities, Cards 3/5/6 only, dialysis ranked first. Re-runs are byte-identical;
  supersede path covered in `tests/test_engine.py`. Regenerate with `UPDATE_GOLDEN=1`.
- API: `GET /scenarios`, `GET /events?scenario=&at=&county=`, `GET /events/active`,
  `GET /action-items?scenario=&at=&facility=&role=&card=&status=` (compact rows),
  `GET /action-items/{id}`, `POST /action-items/{id}/status`,
  `GET /facilities/{id}/action-items?role=&at=`, `GET /cards`, `GET /reference/counties`,
  gzip middleware.
- **Playback view** (`/playback`, from `docs/playback-view.md`): Leaflet map, county layer
  colored by the most severe active event, facility markers sized by affected panel, a
  time scrubber with play/pause and speed, an acuity-ranked event board, and a facility
  drill-down with fired cards, sized panels ("how was this computed?" provenance), role
  toggle (care team / patient / caregiver), verbatim card text, safety line, escalation.
  `make serve` then open http://localhost:8000/playback.
- Connecticut: `fixtures/reference/ct_legacy_county_crosswalk.csv` (legacy county →
  planning regions by grid-sampled area share, builder `scripts/build_ct_crosswalk.py`);
  `UgcResolver` translates NWS legacy CT codes, so CT alerts now match facilities.
- `make lint test`: green.

**Decisions.**
- Heat cards now also fire on `Excessive Heat Watch` / `Extreme Heat Watch`: the watch is
  the 3–7-day lead signal the cards are designed around (the library names the advisory
  and warning only). **Confirm with the clinical reviewer.** Watches are superseded by the
  warnings that follow, so the map shows the escalation.
- OpenFEMA declarations are context, not triggers (no card lists them), matching
  requirements §4.
- Caregiver items are generated only when a card has caregiver content (none in v1).
- Item volume is high (a warning over 20 counties × 3 cards × 2 roles × facilities); the
  compact `/action-items` rows keep the playback page responsive; detail is per item.

**Next:** M5 — dashboard/event board and patient view as server-rendered pages sharing the
playback's API; scenario switcher + live toggle; `make demo`.

## 2026-09-20 — M3: denominators (done)

**Done.**
- Reference tables: `fixtures/reference/places_county.csv` (CDC PLACES 2025 county release,
  10 measures) and `vetpop_county.csv` (VetPop2023 Table 9L, 2023–2030 projections) with
  builders `scripts/build_places.py` / `build_vetpop.py` (new deps: `openpyxl` to read the
  VetPop workbook, `types-openpyxl` for mypy).
- Catchments (`geography/catchment.py`): county → nearest anchor station (VAMC/HCC);
  non-anchor facilities map to a station by health care system (else nearest). Persisted in
  `county_catchment` and `facility_station` tables by `make load`.
- `denominators.py`: `ReferenceTables` + `PanelEstimator` producing `Estimate` objects
  (value, formula, inputs, sources, caveats, components). Rate paths: VA-literature rate on
  the `vha_users` scope, national count allocated by veteran share, PLACES county rate;
  card panels add profile class shares (`panel_multipliers`) and sub-panels (Card 3).
- `GET /facilities/{id}/panels[?card=]` returns sized panels with provenance.
- National sanity anchors in the profile, checked by `make load` and a test: veterans total
  vs VetPop 17,260,286 (±5%), heart-failure panel vs ~510k VHA HF patients (±20%).
- `make lint test`: green. Example: Portland VAMC ≈ 84k veterans in catchment (9 counties); Card 4
  panel ≈ 1.3k.

**Decisions.**
- Anchors are stations, not clinics: with CBOCs as anchors, most VAMCs received no
  counties (a CBOC is usually nearer to a county centroid), which broke the demo's
  "Portland VAMC with sized panels". Panels live at the station; clinics inherit.
- VA-literature rates ("of VHA enrollees / VA patients") are applied to veterans × 0.50
  (`scopes.vha_users`, VHA enrollees ≈ 9.1M / 18.3M veterans). Without this, HF came out
  at 855k vs the 510k anchor. **The 0.50 share needs verification before real use.**
- PLACES 2024/2025 have no CKD measure; the plan's CKD column is dropped (no v1 card sizes
  on CKD; it is a Card 1 risk flag only).
- VetPop territory rows are spread evenly over the territory's counties (PR ≈ 69k veterans
  over 78 municipios); "Foreign Countries" is excluded from `national_veterans`.
- Connecticut: VetPop, PLACES and the Census 2023 boundaries all use the 2022 planning
  regions (09110–09190), but NWS SAME/UGC codes use legacy counties (09001–09015). **M4
  needs a CT legacy-county → planning-region crosswalk** or CT alerts will not match.

**Also:** `docs/playback-view.md` drafts the map playback (time scrubber over a scenario)
for M5.

**Next:** M4 matching engine + action-item store.

## 2026-09-20 — M2: event providers + replay scenarios (done)

**Done.**
- CAP-derived `Event` model (source, type, CAP severity/urgency/certainty, onset/expires,
  geography keys: county FIPS, UGC, ZIPs, polygon; metrics; scenario; raw_ref) and an
  `events` table with upsert by natural key `source:source_id` (`store.py`).
- Providers (`providers/`): `NWSAlertsProvider` (api.weather.gov `/alerts/active`, SAME +
  UGC → counties via the NWS zone-county correlation file), `OpenFEMAProvider`
  (declarations grouped per disaster, county rows), `HMSSmokeProvider` (daily shapefiles →
  one event per day × density, counties by approximate polygon coverage), `AirNowProvider`
  (`/aq/data/` monitoring-site bbox endpoint from AirNow's retained list; monitors →
  counties by point-in-polygon), `ReplayProvider` (fixture `events.json`).
- Reference: `fixtures/reference/nws_zone_county.csv` (NWS bp16ap26.dbx, 4,848 rows) built
  by `scripts/build_nws_zones.py`.
- Three replay scenarios built from archived real data with per-scenario `build.py` and raw
  files kept in git (`fixtures/events/README.md` has provenance and gaps).
- `make ingest` (`scripts/ingest.py`): `EVENT_MODE=replay` loads all three scenarios
  (96 events) — verified into SQLite and the compose Postgres; `EVENT_MODE=live` ingested 87
  real events (78 NWS, 3 OpenFEMA, 6 HMS) into the same table. `make scenarios` rebuilds.
- `make lint test`: green.

**Findings / corrections.**
- api.weather.gov keeps no alert history (2021/2022 windows return empty), so archived
  alerts come from the Iowa Environmental Mesonet VTEC archive (`watchwarn.py` CSV), parsed
  by `providers/iem_archive.py` into the same Event model.
- NWS renumbered WA/OR/ID public zones after 2021; the current zone-county file lacks
  e.g. ORZ006/WAZ558. Dated zone geometries from IEM (`/api/1/nws/ugcs.geojson?valid=`)
  are intersected with county polygons to resolve them (heat dome: 129 counties, 0
  unresolved). Same for two 2022 FL zones.
- NWS Air Quality Alerts are non-VTEC and absent from the archive; the smoke scenario is
  HMS-only. The live provider tracks "Air Quality Alert".
- AirNow: the detailed endpoint docs are login-gated. The provider targets `/aq/data/`
  ("Observations by Monitoring Site", in the retained 2026 list) rather than the retiring
  ZIP/lat-long observation services. **Response shape unverified until a key exists** —
  first live run should be checked against `fixtures/live/raw/airnow_data_*.json`.
- `NWS_USER_AGENT` in `.env` is still empty; the live run used a repo-URL contact string
  passed on the command line. Set it in `.env` for `make ingest` live.
- No new dependencies (pyshp reused for HMS shapefiles).

**Next:** M3 denominators (CDC PLACES county measures × VetPop × profile multipliers).

## 2026-09-20 — M1: facility spine + geography (done)

**Done.**
- `Facility` model; VA Facilities **v1** client (`providers/va_facilities.py`) with paging,
  raw-page caching, JSON:API → GeoJSON conversion; parser tested against a hand-written v1
  page sample derived from the public OpenAPI document, plus a mocked two-page pull.
- ZIP → county crosswalk fixture (`fixtures/reference/zip_county.csv`, 33,791 ZIPs) built
  from the Census 2020 ZCTA↔county relationship file; HUD USPS used automatically when
  `HUD_API_TOKEN` is set. Loader + attribution (`geography/`) with an unresolved report.
- SQLAlchemy store (`store.py`, SQLite fallback or Postgres) with upsert by facility id;
  FastAPI `GET /health`, `GET /facilities[?state=&visn=&county=]` (GeoJSON), `GET /facilities/{id}`.
- `make reference` (build fixtures), `make load` (attribute + persist, exit 1 if any facility
  lacks county/VISN), `make serve`. Network contract test is `@pytest.mark.network`, skipped
  without the key.
- Live pull done with the user's key: **1,400 health facilities** from `sandbox-api.va.gov`
  (self-service keys are sandbox-only; the builder retries against sandbox on a production
  401). Cached to `fixtures/reference/facilities.geojson` with raw pages.
- County attribution switched to **point-in-polygon** on facility coordinates against Census
  1:5m county boundaries (`fixtures/reference/counties.geojson`, builder
  `scripts/build_county_boundaries.py`, new dep `pyshp` to read the shapefile), with the ZIP
  crosswalk as fallback. ZIP-only missed 22 facilities including seven VAMCs on institutional
  ZIPs (15240, 23249, 84148, …) that are not ZCTAs; the 1:20m boundary file omits Guam and
  other territories, hence 1:5m.
- **Done when verified:** 1,399/1,400 facilities resolve to county + VISN; the sole exception
  is `vha_358` Manila VA Clinic (Philippines, no US county), pinned by a golden test
  (`test_m1_done_when_every_health_facility_resolves`). Loaded into both SQLite and the
  docker-compose Postgres.
- `.env` support: every `make` target passes `--env-file .env` to `uv run` when the file
  exists; `.env.example` defaults `DATABASE_URL` to SQLite.
- `make lint test`: green.

**Findings / corrections.**
- Facilities API v0 is gone (`/v0/facilities/all` → 404). v1 has no `/facilities/all` and no
  GeoJSON media type; the plan's "must request GeoJSON or CSV" note was v0-era. CLAUDE.md
  constraint 6 updated. The `search-va-facilities-api` skill's v1 base path was right.
- data.va.gov `9hbf-9jzg` (VISN/market/county) is a broken FY2017 blob; no tabular substitute
  found. VISN comes from the facility record; **market attribution is not available** (a
  `market` column exists, left null). Revisit if a source turns up.
- HUD crosswalk needs a token; Census ZCTA fallback documented with its caveats in
  `fixtures/reference/README.md`.
- Deprecation warnings from starlette's TestClient about httpx are upstream noise.

**Next:** M2 event providers (NWS alerts, AirNow, HMS smoke, OpenFEMA, replay) and the three
fixture scenarios. The county boundary index built here can serve HMS polygon → county
intersection if PostGIS friction appears.

## 2026-09-20 — M0: scaffolding + card library (done)

**Done.**
- Repo scaffolded at `medtask/med-extreme-events/` per `docs/implementation-plan.md` §2;
  planning docs moved from `medtask/docs/` into `docs/`; `CLAUDE.md` at repo root; `git init`
  (no commits yet).
- Tooling: `uv` + `pyproject.toml` (Python 3.12, hatchling), `Makefile` (`lint`, `test`,
  `schema`, `skills`, `skills-check`, `db-up/down`; `ingest`/`demo` stubbed until M2/M5),
  `docker-compose.yml` (postgis/postgis:16-3.4), GitHub Actions CI (`make lint test`).
- Card schema as Pydantic v2 models in `src/xevents/models.py`; `cards/card.schema.json`
  is generated from them (`make schema`) and a test fails if it drifts.
- Six cards transcribed to `cards/0N-*.yaml`. Patient-facing sentences are verbatim from
  `docs/card-library.md` and a test enforces that.
- `profiles/va.yaml`: denominator anchors, acuity order, channels, hooks, default escalation
  template. Cards reference profile keys; a test checks every reference resolves.
- Loader (`src/xevents/cards.py`) rejects: unknown fields, untiered claims, a `weak` tier,
  unknown source ids, duplicate ids/numbers, medication cards without
  `safety.do_not_stop_medication: true`, and malformed YAML — each with a file-anchored
  message. Six malformed fixtures under `tests/fixtures/cards/invalid/`.
- Data-source skills reused from `../../nyc2026-dataset` without copying: `make skills`
  symlinks a curated subset into `.claude/skills/`; verified with a headless `claude -p` run
  that all seven are discovered. `--add-dir` documented as the way to get the full set.
- `make lint test`: green (ruff, ruff format, mypy --strict, 29 tests).

**Decisions.**
- `event_trigger` (singular, in the plan) became `event_triggers: [...]` — any listed
  trigger fires the card. Needed because Cards 5/6 fire on hurricane *or* forecast outage.
- Evidence tiers are `strong | inferential | expert_guidance` (requirements §8). `weak` is
  not representable, so weak/folklore claims cannot be published. Claim-level tiers were
  assigned per the card library's own tier definitions (case reports and non-significant
  subgroups → `inferential`); card-level `evidence_tier` must match the tier of at least one
  claim. **Needs clinical reviewer confirmation.**
- Heat triggers list both `Excessive Heat Warning` (pre-2025 NWS name, used by the 2021
  heat-dome fixture) and `Extreme Heat Warning` (current name).
- Terminology bindings: conditions as ICD-10-CM, medication classes as ATC, devices as
  `local`/`empower` codes. Engineering placeholders for M3/M4 selectors — **not clinically
  reviewed**.
- `actions.caregiver` is empty on all six cards: the card library has no caregiver-addressed
  text and we do not author clinical language in code. Requirements §6 says caregiver mode
  is "the same content addressed to the caregiver"; treat as content-authoring work for a
  reviewer, or a rendering rule in M5 with a profile-templated preamble.
- New dependencies (all boring, per constraint 7): runtime `pydantic`, `pyyaml`, `fastapi`,
  `uvicorn`, `sqlalchemy`, `psycopg[binary]`, `httpx`, `jinja2` (the §2 stack); dev
  `pytest`, `ruff`, `mypy`, `types-PyYAML`, `jsonschema` (validates cards against the
  checked-in JSON Schema so the file is real, not documentation).

**Risks / follow-ups for M1.**
- `search-va-facilities-api` skill documents base path `services/va_facilities/v1`; the plan
  says v0 with `/facilities/all` GeoJSON. Verify with a real key before writing the client.
- Denominator numbers in `profiles/va.yaml` are the card library's planning anchors; M3
  replaces/augments them with PLACES × VetPop.

**Next:** M1 — facility spine + geography (VA Facilities API client, VISN/Market/County
crosswalk, HUD ZIP↔county, cached pulls into `fixtures/reference/`).
