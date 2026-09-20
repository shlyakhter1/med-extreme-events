# PROGRESS

Short dated entries, newest first. One milestone per session (M0 → M5).

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
