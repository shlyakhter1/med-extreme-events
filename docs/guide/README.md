# Design and user guide

*As of 2026-09-21, after the first demo.*

This guide explains how the system is built and how to use it. It describes the code as it
is today. The planning documents it grew from are `docs/requirements.md` (what the system
should become) and `docs/implementation-plan.md` (the M0–M5 milestones).

The system has two layers that will be separated further, and each has its own document:

| Document | Covers |
| --- | --- |
| [events-and-playback.md](events-and-playback.md) | **Event layer.** Pulls weather and environmental feeds, normalizes them into one event model, resolves them to counties, stores them, and plays them back on a map. It knows nothing about medicine. |
| [medical-layer.md](medical-layer.md) | **Medical layer.** Holds the VA facilities, their catchments and estimated patient panels, and the six clinical playbook cards. It matches events to cards and turns each match into action items for care teams and patients. |
| [data-sources.md](data-sources.md) | Every external source: what it provides, how it is fetched and cached, which layer uses it, and its known gaps. |

## The system in one paragraph

An event feed reports that something is happening in a set of counties: a heat warning, a
hurricane watch, a smoke plume. The VA facilities that own a patient panel in those counties
come into scope. Every clinical card whose trigger matches the event produces one action item
for each audience at each facility. Each item carries the card's reviewed text, and its panel
size is estimated from public aggregate data. Nothing in the system is about an individual
patient. This is **Mode A** (aggregate, no PHI), and every number carries the formula and
sources that produced it.

## Architecture

```mermaid
flowchart LR
  subgraph EV[Event layer]
    F[Feeds<br/>NWS · IEM archive · HMS · OpenFEMA · AirNow] --> P[Providers<br/>live + replay]
    P --> ES[(events)]
    G1[(Counties · NWS zones)] --> P
    ES --> PB[Playback · Events pages]
  end
  subgraph MED[Medical layer]
    FAC[(Facilities · catchments)] --> ENG[Matching engine]
    CARDS[(Cards · VA profile)] --> ENG
    DEN[(VetPop · PLACES)] --> PAN[Panel estimator] --> ENG
    ENG --> AI[(action_items)]
    AI --> UI[Dashboard · facility page · patient view]
  end
  ES -- Event model, county FIPS --> ENG
  AI -. overlay .-> PB
```

**The seam between the layers is the `Event` record** (`src/xevents/models.py`) and its
list of county FIPS codes. The engine reads events and nothing else from the event layer.
The event layer never reads cards, panels or action items, with one exception: the
playback page overlays action items and cards on its map (see
[events-and-playback.md §7](events-and-playback.md#7-what-couples-this-layer-to-the-medical-layer)).

**Shared foundation.** Both layers use the county geography (`fixtures/reference/counties.geojson`,
`src/xevents/geography/`), one database (`src/xevents/store.py`) and one FastAPI app
(`src/xevents/api.py`, `src/xevents/web/`).

## Quick start

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/). No API key, no database server and
no network: the reference data and replay scenarios are committed.

```sh
make demo      # fresh SQLite → facilities + catchments → replay events → action items → serve
```

After about a minute, open:

| Page | For |
| --- | --- |
| <http://localhost:8000/playback> | Scrub a scenario through time on the US map (event layer, with card overlay) |
| <http://localhost:8000/dashboard/events> | Every event, with its window, geography and metrics (event layer) |
| <http://localhost:8000/> | Care-team dashboard: event board, outreach queue, map (medical layer) |
| <http://localhost:8000/dashboard/facilities/vha_648> | One facility's fired cards, panels and checklist (medical layer) |
| <http://localhost:8000/demo/patient-view?facility=vha_648> | What a patient or caregiver would see (medical layer) |
| <http://localhost:8000/docs> | Interactive API reference |

Every page states that **times are UTC**. For containers, hosting and live mode, see
[`docs/deploy.md`](../deploy.md).

### Configuration

Copy `.env.example` to `.env`, which is gitignored. Every `make` target loads it.

| Variable | Needed for | Default |
| --- | --- | --- |
| `EVENT_MODE` | `replay` or `live` for `make ingest match` | `replay` |
| `DATABASE_URL` | Postgres, or the SQLite fallback | `sqlite:///xevents.db` (`make demo` uses `demo.db`) |
| `NWS_USER_AGENT` | Live NWS pulls. NWS blocks requests without a contact string | none |
| `VA_FACILITIES_API_KEY` | Rebuilding `facilities.geojson` only (`make reference`) | none |
| `AIRNOW_API_KEY` | Live air-quality events. Skipped when unset | none |
| `HUD_API_TOKEN` | Optional HUD ZIP↔county crosswalk. Census ZCTA is used otherwise | none |

**Never commit a key.** `.env.example` must hold empty assignments only.
`tests/test_secrets.py` fails the build if a tracked file assigns a credential-shaped value
to a secret-named variable.

### Make targets

| Target | Does |
| --- | --- |
| `make demo` | The whole replay pipeline into a fresh `demo.db`, then serves |
| `make load` | Loads reference data, attributes facilities to county and VISN, builds catchments |
| `make ingest` | Loads events (`EVENT_MODE=replay`: all scenarios; `live`: real feeds) |
| `make match` | Runs the engine over stored events and writes action items |
| `make serve` | Serves the API and pages on :8000 with reload |
| `make reference` | Rebuilds the cached reference data from its sources (network; facilities need a key) |
| `make scenarios` | Rebuilds the replay fixtures from their archived raw files |
| `make schema` | Regenerates `cards/card.schema.json` from the Pydantic models |
| `make lint test` | ruff, mypy --strict and pytest. Must stay green |

## Guarantees the design depends on

These come from `CLAUDE.md`, and tests enforce most of them.

1. **No PHI, no synthetic patients.** Panels are aggregate estimates with provenance.
2. **The engine is pure.** `src/xevents/engine.py` does no I/O. The same inputs always produce
   the same action items, and two golden tests pin the replay output exactly.
3. **Clinical text comes only from card YAML.** Code copies it verbatim and never
   generates, paraphrases or "improves" it.
4. **Nothing advises stopping or changing a medication.** Every medication card carries the
   templated "Don't stop your medication — contact your care team."
5. **No VA fact is hard-coded.** Prevalence, acuity order, channels and hooks live in
   `profiles/va.yaml`. Clinical content lives in `cards/*.yaml`.
6. **An empty board is never an all-clear.** Live mode shows feed freshness, and a stale feed
   is flagged.
7. **Every external call is cacheable.** Providers are the only network code, and every
   fixture can be rebuilt from its raw files.

## Where to go next

- `docs/card-reference-for-frontend.md`: API shapes and rendering rules for anyone building
  a UI on the action items.
- `docs/card-library.md`: the clinical source of truth for all six cards.
- `PROGRESS.md`: the dated log of what was built, what was decided, and what still needs a
  clinical reviewer.
