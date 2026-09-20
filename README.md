# med-extreme-events

Mode A (aggregate, no-PHI) demo that maps forecast extreme events (heat, hurricane/flood,
wildfire smoke, air pollution, power outage) onto VA facilities and their estimated at-risk
panels, producing playbook-card action items for care teams, patients, and caregivers.

Read first: `CLAUDE.md`, then `docs/implementation-plan.md` (milestones M0–M5),
`docs/requirements.md`, and `docs/card-library.md` (the reviewed clinical content).

## Quick start

```sh
uv sync           # Python 3.12 venv with runtime + dev deps
make lint test    # ruff + mypy, then pytest
make schema       # regenerate cards/card.schema.json after editing src/xevents/models.py
make db-up        # postgres + postgis via docker compose (optional; SQLite is the default)
make reference    # build cached reference data (facilities needs VA_FACILITIES_API_KEY)
make load         # facilities + catchments into the DB
make ingest       # events: EVENT_MODE=replay (three scenarios) or live
make match        # action items from stored events
make serve        # API + playback view at http://localhost:8000/playback
```

## Layout

```
cards/            six v1 playbook cards as YAML + card.schema.json (generated)
profiles/va.yaml  VA denominators, acuity order, channels, care-system hooks
fixtures/         replay scenarios (events/) and cached reference data (reference/)
src/xevents/      models, card/profile loaders; providers/engine/store/api land in M1–M5
tests/            schema-validation tests incl. malformed-card rejection
scripts/          export_card_schema.py, link_skills.py
```

## Data-source skills (shared repo, not copied)

Agent Skills for the public data sources this demo uses (VA Facilities API, AirNow, CDC
PLACES, CDC heat-and-medications guidance, NOAA daily summaries, evidence graphs) live in the
sibling repo `../nyc2026-dataset` and are used in place. See "Data-source skills" in
`CLAUDE.md` for how to launch Claude Code so they load, and `make skills` for the optional
symlink shortcut.
