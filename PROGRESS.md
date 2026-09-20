# PROGRESS

Short dated entries, newest first. One milestone per session (M0 → M5).

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
