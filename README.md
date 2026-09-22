# med-extreme-events

Maps forecast extreme events (heat, hurricane/flood, wildfire smoke, air pollution, power
outage) onto VA facilities and their estimated at-risk panels, and turns reviewed clinical
playbook cards into action items for care teams, patients and caregivers.

Aggregate mode only: **no PHI, no patient records, real or synthetic.** Every number is an
estimate that carries the formula, inputs and sources that produced it.

## Run it

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/). No API key, no database server and
no network access: the reference data and the five replay scenarios are in this repository.

```sh
make demo          # empty state → facilities → replay events → action items → serve
```

About a minute, then open:

| | |
| --- | --- |
| <http://localhost:8000/> | Monitor: live now (last 2 weeks) or a replay, on a map with cards, facilities and a timeline |
| <http://localhost:8000/replays> | Scenarios: what each replay shows, with guided moments |
| <http://localhost:8000/card-library> | Cards: the eight playbook cards in full |
| <http://localhost:8000/sources> | Data sources: coverage, limits and last live run |
| <http://localhost:8000/dashboard/events> | Every event, with its window, geography and metrics |
| <http://localhost:8000/demo/patient-view?facility=vha_648> | What a patient or caregiver sees |
| <http://localhost:8000/docs> | Interactive API reference |

Or as a container, which bakes the same database at build time:

```sh
docker build -t med-extreme-events:demo . && docker run --rm -p 8000:8000 med-extreme-events:demo
```

**Hosting it on the web, live mode, pip instead of uv, and Postgres: see
[docs/deploy.md](docs/deploy.md).**

### The five scenarios

| Scenario | What fires |
| --- | --- |
| `heat_dome_2021` | Pacific Northwest heat dome. Cards 1, 2 and 4 across 70 WA/OR/ID facilities |
| `ian_2022` | Hurricane Ian. Cards 3, 5 and 6 across 81 Florida facilities, dialysis ranked first |
| `smoke_nyc_2023` | Canadian wildfire smoke over New York, June 2023. Card 8 across Northeast facilities |
| `uri_2021` | Winter Storm Uri, Texas, February 2021. Card 7 from cold products (legacy Wind Chill names normalized), Cards 3, 5 and 6 from 12,900 hourly EAGLE-I county outage measurements, cold × outage boost |
| `smoke_canada_2026` | Canadian wildfire smoke, July 2026, Upper Midwest to the Northeast, with the central-US heat dome. Card 8 from AirNow AQI and HMS smoke, Cards 1, 2 and 4 where heat co-occurs |

### Other commands

```sh
uv sync                    # just the virtualenv
make load ingest match     # the demo pipeline, one stage at a time
make serve                 # the server on its own
make lint test             # ruff + mypy + pytest
make reference             # rebuild cached source data (needs VA_FACILITIES_API_KEY)
make scenarios             # rebuild the replay fixtures from their archived sources
EVENT_MODE=live make ingest match   # real feeds: NWS alerts (+2-week archive), FEMA, NOAA smoke, EAGLE-I outages
```

## How it works

An event feed fires for a county, the facilities in that county come into scope, each card
whose trigger matches produces one action item per role, and the affected panel is sized
from aggregate data. The matching engine is pure and deterministic: the same events always
produce the same action items, which five golden tests pin exactly.

```
cards/            eight reviewed playbook cards as YAML + generated JSON Schema
docs/carbon.yaml  display-only medication carbon estimates (methods in carbon-footprint.md)
profiles/va.yaml  VA denominators, acuity order, channels, care-system hooks
fixtures/         replay scenarios (events/) and cached reference data (reference/)
src/xevents/      models · providers · geography · denominators · engine · store · api · web
tests/            unit, schema, golden-scenario and page tests
```

**Start with the [design and user guide](docs/guide/README.md)**. It describes the event
layer (feeds, event store, playback) and the medical layer (facilities, panels, cards,
action items) separately, and lists every data source and how it is used.

Contributors: read `CLAUDE.md` first, then `docs/implementation-plan.md` for the milestones,
`docs/requirements.md` for the system concept, and `docs/card-library.md` for the clinical
content, which is the source of truth for every patient-facing sentence.

Building a UI against this? Start with
**[docs/card-reference-for-frontend.md](docs/card-reference-for-frontend.md)** — what is in
each card, the API shapes, and the rules for rendering clinical text.

`PROGRESS.md` is the running log: what each milestone did, what was decided, and what still
needs a clinical reviewer.

## Data sources

All public, all cached into `fixtures/reference/` with retrieval dates: VA Lighthouse
Facilities API, NWS alerts (plus the Iowa State VTEC archive for historical replays), NOAA
HMS smoke polygons, OpenFEMA declarations, AirNow (live API and the keyless public file
archive), DOE/ORNL EAGLE-I county power outages with the Moehl county customer counts, HHS
emPOWER electricity-dependent DME counts, CDC PLACES, VA VetPop, and Census county boundaries
and ZCTA crosswalks.

Agent Skills for these sources live in the sibling repository `../../nyc2026-dataset` and
are used in place, never copied. See "Data-source skills" in `CLAUDE.md`.
