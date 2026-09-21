# CLAUDE.md — VA Extreme-Event Decision-Support Demo

## What this project is

A Mode A (aggregate, **no-PHI**) demo that maps forecast extreme events (heat, hurricane/flood, wildfire smoke, air pollution, power outage) onto VA facilities and their estimated at-risk panels, producing playbook-card action items for care teams, patients, and caregivers.

Read before any work:
- `docs/implementation-plan.md` — milestones M0–M5, each with a *Done when*
- `docs/implementation-plan-v2.md` — milestones M6–M10 (temporality, EAGLE-I outages, emPOWER, Cards 7–8)
- `docs/requirements.md` — system concept, data model, architecture (§7 has the action-item schema)
- `docs/requirements-v2.md` — temporality axis, trigger schema v2, outage provider, co-occurrence boost (settled decisions; do not reopen)
- `docs/card-library.md` — the six clinical cards; the source of truth for all card YAML content
- `docs/card-library-additions.md` — Cards 7, 8 and the Card 6 addendum; the only source for their clinical strings

Repo home: `shlyakhter1` GitHub. Stack: Python 3.12, FastAPI, SQLAlchemy + PostgreSQL/PostGIS (SQLite+SpatiaLite fallback), Pydantic v2, httpx, Jinja2 + htmx, pytest, ruff + mypy, Makefile entry points.

## Hard constraints — never violate

1. **No PHI, no synthetic patient records.** Mode A only: panels are aggregate estimates with provenance (formula + inputs attached to every number).
2. **Never hard-code a VA fact** (prevalence, channel, hook) outside `profiles/va.yaml` or `cards/*.yaml`.
3. **The matching engine stays pure** — no I/O in `engine.py`; providers are the only network code; every external call cacheable to `fixtures/`.
4. **Patient-facing strings come only from card YAML** — never generated, paraphrased, or "improved" in code. Clinical language is reviewed content.
5. **Never advise stopping or changing a medication dose** anywhere in generated output; "contact your care team" is the templated escalation.
6. **API etiquette:** NWS requires a User-Agent header (`NWS_USER_AGENT` env); AirNow is limited to 500 req/h — cache aggressively and use only the 2026 consolidated endpoints (legacy retired Sep 30, 2026); VA Facilities API key from `VA_FACILITIES_API_KEY` as an `apikey` header. Facilities API **v1** only (v0 and its `/facilities/all` GeoJSON endpoint are gone, verified 2026-09-20): page `GET /facilities?type=health&page=&per_page=` as JSON:API and build GeoJSON ourselves.
7. **Prefer boring choices.** No new dependencies without a note in `PROGRESS.md`.

## Working agreement

- One milestone per session, in order M0 → … → M5 (`docs/implementation-plan.md`), then M6 → … → M10 (`docs/implementation-plan-v2.md`).
- A milestone is finished only when its *Done when* in the implementation plan is verified and `make lint test` is green.
- End every session with a short dated entry in `PROGRESS.md`: what was done, decisions made, what's next.
- Golden scenario tests are the engine's contract: replaying `fixtures/events/heat_dome_2021` and `ian_2022` must produce the expected action-item sets exactly.
- Fixtures are rebuildable: each scenario directory keeps raw source files, a README with retrieval date + URLs, and a builder script.

## v2 invariants (requirements-v2 §8)

- Every `Event` must carry `temporality` (`forecast | imminent | observed`); provider mapping tables are data, and the raw source basis is preserved in `metrics` (`temporality_basis`, `raw_nws_event`).
- EAGLE-I attribution string is mandatory wherever outage data renders: "Electric customer outage data provided by EAGLE-I, Department of Energy." Customers are meters, not people — say so in provenance.
- emPOWER numbers are always labeled as measured Medicare proxy; they never replace veteran denominators.
- Cards 7/8 clinical strings come only from `docs/card-library-additions.md`; legacy NWS cold-product names are normalized in the provider (`LEGACY_NWS_EVENT_NAMES`), never listed in cards.
- No compound trigger grammar — compounding is the engine co-occurrence boost only (backlog item for grammar). Cross-family supersede pairs live in `engine.SUPERSEDE_FAMILIES`, not in cards.

## Environment

```
AIRNOW_API_KEY=        # free at docs.airnowapi.org
VA_FACILITIES_API_KEY= # free at developer.va.gov
NWS_USER_AGENT=        # "med-extreme-events-demo (contact: <email>)"
EVENT_MODE=replay      # replay | live
DATABASE_URL=          # postgres via docker-compose, or sqlite fallback
EAGLEI_TOKEN=          # ArcGIS token for FEMA's partner EAGLE-I FeatureServer (token-gated)
EAGLEI_FEATURE_URL=    # or a public EAGLE-I mirror layer with the same fields
```

## First task (M0)

Scaffold the repo per `docs/implementation-plan.md` §2, define the card JSON Schema per M0, transcribe the six cards from `docs/card-library.md` into `cards/*.yaml`, and make `make lint test` pass with schema-validation tests (including rejection of a malformed card). Stop and summarize before M1.

## Data-source skills (shared repo, used in place)

Agent Skills for the public data sources this demo pulls from live in the sibling repo
`../../nyc2026-dataset` (canonical path `.agents/skills/<name>/SKILL.md`). They are **never
copied** into this repo; two mechanisms make them available here:

1. **Symlinks (default, committed).** `make skills` links a curated subset into
   `.claude/skills/` as relative symlinks (manifest: `LINKED_SKILLS` in
   `scripts/link_skills.py`). Claude Code discovers them as project skills; `make skills-check`
   verifies every link resolves. If the skills repo lives elsewhere:
   `make skills SKILLS_REPO=/path/to/nyc2026-dataset`. Add a skill by adding a manifest line
   and re-running `make skills` — not by copying files.
2. **`--add-dir` (full set + file access).** Launch `claude --add-dir ../../nyc2026-dataset` to
   expose every skill in that repo and to let Claude read their `references/` and cached
   `datasets/` without permission prompts. Prefer this when a milestone needs a skill that
   is not in the manifest.

Rules when using them:
- Each `SKILL.md` has a `## Search trigger` section: follow it (live fetch vs. cached notes).
- Socrata-backed skills share `nyc2026-dataset/references/socrata-soda-api.md`; read it once.
- Skills in that repo's "Private Datasets" section are internal-use; do not cache their
  data into `fixtures/` or any public artifact.
- A skill's verified URLs beat prior knowledge; if they disagree with this repo's docs
  (e.g. Facilities API v0 vs v1 base path), re-verify with a real fetch and record the
  outcome in `PROGRESS.md`.

Milestone → skill map: M1 `search-va-facilities-api`; M2 `search-epa-airnow-aqs`,
`search-noaa-ncei-daily-summaries`; M3 `search-cdc-places`; card evidence
`search-cdc-heat-medications-guidance`, `search-system-climate-research`,
`search-harvard-dataverse-graph-snapshot`.
