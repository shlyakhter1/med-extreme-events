# VA Extreme-Event Demo — Implementation Plan v1

*As of 2026-09-20*

Build plan for the first demo implementation, written to hand to Claude Code. It implements Mode A (aggregate, no-PHI) of `docs/requirements.md`, loading the six cards from `docs/card-library.md` as structured rules.

## 1. Demo Scope & Success Criteria

**In scope (Mode A, no PHI anywhere):** the six v1 cards as structured rules; live + replay event feeds; all VA health facilities with county/VISN attribution; aggregate denominators; matching engine producing persisted action items; a care-team dashboard and a read-only patient/caregiver view rendered from the same API; two replay scenarios end-to-end.

**Success criteria (the demo passes when all are true):**
1. Replaying the 2021 PNW heat dome fires Cards 1, 2, 4 for the correct WA/OR facilities, each with a sized panel estimate and rendered clinician + patient content.
2. Replaying Hurricane Ian fires Cards 3, 5, 6 for Florida facilities, with the dialysis card ranked first by acuity.
3. Flipping `EVENT_MODE=live` pulls today's real NWS/AirNow data with zero code change and renders whatever is actually active.
4. Every displayed number and claim is traceable in the UI to its source (event id, denominator formula, card citation).
5. Full pipeline rebuilds from empty with one command (`make demo`), under 10 minutes, network available.

**Explicitly out:** authentication, real patient data or FHIR calls, notifications (SMS/push — stub the channel adapter), CDS Hooks, HeatRisk raster ingestion (documented stub; alerts-based heat triggers only), card-authoring UI (cards are files in the repo).

## 2. Tech Stack & Repo Layout

Python 3.12, FastAPI, SQLAlchemy + PostgreSQL (PostGIS) via docker-compose — SQLite+SpatiaLite acceptable fallback for zero-install runs; Pydantic v2 models throughout; httpx for feed clients; Jinja2 + htmx for the dashboard (no SPA build step); pytest; ruff + mypy; Makefile as the entry point. Cards and profiles are YAML validated by Pydantic schemas at load.

```
med-extreme-events/
├─ Makefile                  # demo, test, lint, db targets
├─ docker-compose.yml        # postgres+postgis
├─ cards/                    # six v1 cards as YAML (+ JSON Schema)
├─ profiles/va.yaml          # denominator tables, channels, hooks
├─ fixtures/                 # replay scenarios + cached reference data
│  ├─ events/heat_dome_2021/ · ian_2022/ · smoke_nyc_2023/
│  └─ reference/             # facilities.geojson, crosswalk.csv, places.csv, vetpop.csv
├─ src/xevents/
│  ├─ models.py              # Event, Card, Facility, ActionItem (Pydantic + ORM)
│  ├─ providers/             # base.py, nws.py, airnow.py, hms.py, openfema.py, replay.py
│  ├─ geography/             # loaders, zip↔county, county→facility catchment
│  ├─ denominators.py        # PLACES × VetPop × profile multipliers
│  ├─ engine.py              # pure matching: (events, cards, panels) → action items
│  ├─ store.py               # persistence + status transitions
│  ├─ api.py                 # FastAPI routes
│  └─ web/                   # templates: dashboard, event drill-down, patient view
└─ tests/                    # unit + scenario tests mirroring src
```

Environment: `AIRNOW_API_KEY` (free registration; new consolidated endpoints only — legacy retire Sep 30, 2026), `VA_FACILITIES_API_KEY` (free), `NWS_USER_AGENT` (contact string per NWS policy), `EVENT_MODE=replay|live`, `DATABASE_URL`.

## 3. Milestones M0–M2

**M0 — Scaffolding + card library.** Repo, tooling, docker-compose, CI (lint+test). Define the card JSON Schema: `id, version, event_trigger {type, conditions e.g. nws_event in ["Excessive Heat Warning","Heat Advisory"]}, population_selector {condition_codes, med_classes, device_classes, flags}, actions {care_team[], patient[], caregiver[]}, escalation[], evidence_tier, sources[], window_days`. Transcribe all six v1 cards to YAML; loader validates and rejects untiered claims. *Done when:* `make lint test` green; six cards load; a seventh malformed card is rejected with a useful error.

**M1 — Facility spine + geography.** Client for VA Facilities API v0: pull `/facilities/all` GeoJSON, filter health facilities, persist id/name/type/lat-lon/county/`operating_status`. Load the VISN/Market/County crosswalk (data.va.gov 9hbf-9jzg) and HUD ZIP↔county; attribute each facility to county → market → VISN. Cache raw pulls into `fixtures/reference/` so the demo never depends on the API being up. *Done when:* every health facility resolves to a county and VISN; a map endpoint returns facilities GeoJSON.

**M2 — Event providers.** `EventProvider` ABC: `fetch(window) -> list[Event]`, with `NWSAlertsProvider` (api.weather.gov `/alerts/active`, UGC zone+county parsing, heat + tropical + flood event types), `AirNowProvider` (new consolidated endpoints, ZIP-keyed AQI, respect 500 req/h via caching), `HMSSmokeProvider` (daily smoke polygons → county intersection via PostGIS), `OpenFEMAProvider` (declarations by county), and `ReplayProvider` (reads a fixture directory, same Event model). Normalize everything to the CAP-derived Event model with geography keys. Build the three fixture scenarios from archived real data. *Done when:* `EVENT_MODE=replay make ingest` loads all three scenarios; `EVENT_MODE=live` ingests real current alerts; both land in the same event store table.

## 4. Milestones M3–M5

**M3 — Denominators.** Load CDC PLACES county measures (COPD, asthma, CHD, diabetes, CKD, depression) and VetPop county veteran counts into reference tables. `denominators.py` computes per (facility, condition-class): `veteran_count(catchment) × rate`, where rate = VA-literature multiplier when the profile provides one (diabetes 0.25, CHF 0.05, schizophrenia 0.036, bipolar 0.030), else the PLACES county rate; med-class sub-panels via profile multipliers (e.g., share of CHF on loop diuretics). Every estimate object carries its formula and inputs for the UI's "how was this number computed" popover. *Done when:* any (facility, card) pair returns a sized panel with provenance; totals sanity-check against national anchors (±20%).

**M4 — Matching engine + action-item store.** `engine.match(events, cards, panels) -> list[ActionItem]` — pure, deterministic, no I/O. Logic: event → counties/ZIPs → facilities in scope → cards whose trigger matches the event → panel size per card → one ActionItem per (event, card, facility, role), acuity-ranked (profile-defined: dialysis > clozapine > insulin > …). Store with status machine `issued→delivered→acknowledged→completed|expired|superseded`; re-running matching upserts by natural key (event, card, facility) — a strengthened alert supersedes, never duplicates. *Done when:* heat-dome replay yields the expected item set (golden-file test); re-runs are idempotent; supersede path covered by test.

**M5 — API + UI.** FastAPI: `GET /events/active`, `GET /facilities`, `GET /facilities/{id}/action-items?role=`, `POST /action-items/{id}/status`, `GET /demo/patient-view?facility=&card=`. Dashboard (Jinja2+htmx): event board ranked by severity×panel, facility drill-down listing fired cards with clinician checklists, and a patient/caregiver rendering of the same items (role toggle). A Leaflet map of facilities colored by active-event status. Scenario switcher (replay pickers + live toggle) in the header. *Done when:* success criteria 1–4 of §1 pass through the browser.

## 5. Testing, Fixtures & Demo Script

**Test layers.**
- Unit: card schema validation, geography crosswalk edge cases (multi-county ZIPs), provider parsers against saved raw payloads, denominator formulas.
- Golden scenario tests: each replay fixture has an expected action-item set checked exactly — the engine's determinism contract.
- Contract smoke tests (network-marked, non-blocking in CI): live NWS/AirNow/Facilities calls parse successfully — catches upstream format drift, including the AirNow migration.
- No mocking of internal modules; only network boundaries use fixtures.

**Fixture provenance.** Each `fixtures/events/<scenario>/` contains raw source files, a `README` with retrieval date and URLs, and a small builder script — fixtures are rebuildable, not hand-edited blobs.

**Demo script (≈10 minutes).**
1. `make demo` — fresh DB, load reference data + cards, ingest heat-dome replay, open dashboard.
2. Show the event board: WA/OR facilities lit, ranked; drill into Portland VAMC — Cards 1/2/4 with sized panels; click a number → provenance popover.
3. Toggle to patient view → plain-language lithium guidance with escalation triggers.
4. Switch scenario to Ian → Florida lights up; dialysis card ranked first; show the acuity ordering rationale.
5. Flip to live mode → whatever is real today renders; point out feed freshness banners.
6. Close on the cards YAML in the editor: "adding a pediatric asthma profile is a data change, not a code change."

## 6. Claude Code Handoff

**Working agreement.** One milestone per session, in order M0→M5; each ends with its *Done when* verified, tests green, and a short `PROGRESS.md` entry. This plan and the card-library doc live in `docs/` and are referenced in `CLAUDE.md` so context survives sessions.

**`CLAUDE.md` seed (constraints Claude Code must honor):**
- No PHI, no synthetic patient records — Mode A only; panels are estimates with provenance.
- Never hard-code a VA fact outside `profiles/va.yaml` or `cards/*.yaml`.
- Engine stays pure (no I/O); providers are the only network code; all external calls cached to fixtures.
- Patient-facing strings come only from card YAML — never generated or paraphrased in code.
- Respect API etiquette: NWS User-Agent header, AirNow 500 req/h with caching, Facilities API key from env.
- Prefer boring choices; no new dependencies without a note in `PROGRESS.md`.

**Task sequence to paste as the first prompt:** "Read docs/implementation-plan.md and docs/card-library.md. Execute M0: scaffold the repo per §2, define the card JSON Schema per M0, transcribe the six cards from the card-library doc into cards/*.yaml, and make `make lint test` pass with schema-validation tests. Stop and summarize before M1."

**Risks to watch during build.**
- Facilities API `/facilities/all` requires GeoJSON/CSV accept headers (JSON:API 406s) — handle in M1.
- AirNow: build only against the 2026 consolidated endpoints.
- HMS polygon→county intersection is the one real geospatial computation — if PostGIS friction stalls M2, ship point-in-polygon on facility coordinates and log the simplification.
- PLACES measures are adults ≥18 and general-population — the provenance popover must say so (requirement G9/§8 of the requirements doc).

**Definition of done for the demo overall:** the five success criteria in §1, plus a recorded run-through of the §5 demo script.

**Resolved decisions.**
- [x] Stack confirmed: Python / FastAPI / htmx
- [x] Headline scenarios: both — 2021 PNW heat dome + Hurricane Ian (smoke NYC 2023 as bonus)
- [x] Repo home: `shlyakhter1` GitHub
