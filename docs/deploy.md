# Running and hosting the demo

Two ways to run it: **locally** with `uv` (best for development) or **as a container**
(best for showing it to someone else). Both default to replay mode, which needs no API key
and no network, because the reference data and the three replay scenarios are committed to
this repository.

---

## 1. Run it locally

Prerequisites: Python 3.12 and [uv](https://docs.astral.sh/uv/). Nothing else — the database
defaults to a SQLite file, so Docker and Postgres are optional.

```sh
git clone https://github.com/shlyakhter1/med-extreme-events.git
cd med-extreme-events
make demo
```

`make demo` builds a fresh SQLite database from an empty state and then serves it:

1. `scripts/load_reference.py` — 1,400 VA health facilities, county attribution, catchments
2. `scripts/ingest.py --mode replay` — the three replay scenarios (96 events)
3. `scripts/match.py --mode replay` — the action items the engine derives from them
4. `uvicorn` on <http://localhost:8000>

It takes about a minute and needs no network access. Then open:

| Page | What it is |
| --- | --- |
| <http://localhost:8000/> | Care-team dashboard: event board, map, active events |
| <http://localhost:8000/playback> | Time-scrubbed playback of a scenario on the US map |
| <http://localhost:8000/dashboard/events> | Every event, with windows, geography and metrics |
| <http://localhost:8000/demo/patient-view?facility=vha_648> | What a patient or caregiver sees |
| <http://localhost:8000/docs> | Interactive API reference (OpenAPI) |

To run the pieces separately instead:

```sh
uv sync                  # create the virtualenv
make load                # facilities + catchments into the database
make ingest              # events   (EVENT_MODE=replay by default)
make match               # action items
make serve               # just the server
make lint test           # ruff + mypy + pytest
```

### Prefer pip over uv?

`requirements.txt` is generated from the lockfile with pinned hashes:

```sh
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src DATABASE_URL=sqlite:///demo.db
python scripts/load_reference.py && python scripts/ingest.py && python scripts/match.py
uvicorn xevents.api:app --port 8000
```

Regenerate it after changing dependencies:

```sh
uv export --no-dev --no-emit-project --format requirements-txt -o requirements.txt
```

### Postgres instead of SQLite

Optional. PostGIS is not required by anything yet — the geometry work is pure Python.

```sh
make db-up                                     # postgres+postgis via docker compose
echo 'DATABASE_URL=postgresql+psycopg://xevents:xevents@localhost:5432/xevents' >> .env
make load ingest match serve
```

---

## 2. Run it as a container

The image bakes the demo database at build time, so the running container needs no API key,
no database server and no network:

```sh
docker build -t med-extreme-events:demo .
docker run --rm -p 8000:8000 med-extreme-events:demo
```

Open <http://localhost:8000>. The image is 381 MB and starts in a couple of seconds; most of
its size is the Python base image plus the county boundary and reference fixtures.

---

## 3. Host it on the web

The container is the unit of deployment everywhere below. Replay mode is stateless: every
request reads the read-only SQLite file baked into the image, so a single small instance is
enough and you can scale to zero between demos.

### Fly.io — fewest steps

`fly.toml` is in the repository.

```sh
brew install flyctl && fly auth login
fly launch --no-deploy --copy-config    # accept the app name or pick your own
fly deploy
fly open
```

`auto_stop_machines` is on, so the machine sleeps when idle and wakes on the next request.
A shared-CPU 1 GB machine is enough and costs roughly a few dollars a month at demo traffic.

### Render — no CLI needed

1. Push this repository to GitHub.
2. In Render, create a **Web Service** and point it at the repository.
3. Runtime **Docker**; leave the build and start commands empty (the `Dockerfile` handles
   both). Render injects `PORT`, which the image already honours.
4. Deploy. The free instance type works; it sleeps when idle.

### Google Cloud Run — scales to zero, generous free tier

```sh
gcloud run deploy med-extreme-events \
  --source . --region us-central1 --allow-unauthenticated --memory 1Gi
```

### Anywhere else

Any host that runs a container works: Railway, Azure Container Apps, AWS App Runner, a
plain VM with `docker run`. The only requirements are one exposed HTTP port and about 1 GB
of memory (the county boundary file is held in memory for point-in-polygon lookups).

---

## 4. Live mode when hosted

Replay mode is the right default for a demo: it is deterministic and nothing can break it.
Live mode pulls current NWS alerts, FEMA declarations and NOAA smoke polygons, so it needs
writable storage and outbound network access.

1. Set `NWS_USER_AGENT` to a contact string. The National Weather Service requires it and
   will block requests without one.
2. Set `AIRNOW_API_KEY` if you want air-quality events (free at
   [docs.airnowapi.org](https://docs.airnowapi.org/account/request/)). Everything else needs
   no key. **The AirNow response shape has not been verified against a real key yet** — check
   the first pull before relying on it.
3. Give the container a writable database. A read-only image database is fine for replay but
   not for live ingestion:

   ```sh
   fly volumes create data --size 1     # then mount it at /data in fly.toml
   # and set DATABASE_URL=sqlite:////data/live.db
   ```

4. Refresh on a schedule — the feeds update continuously and the dashboard banner marks a
   feed stale after six hours:

   ```sh
   EVENT_MODE=live python scripts/ingest.py && python scripts/match.py --mode live
   ```

   Live ingestion loads the **trailing two weeks** of NWS watches, warnings and advisories
   from the Iowa State VTEC archive, plus whatever is in force right now from
   `api.weather.gov`. `/alerts/active` alone reports only the current instant, so a live view
   built on it empties out whenever the weather is calm. Change the window with
   `--lookback-days N`. Duplicates between the two sources are dropped by matching product
   name, counties and onset hour.

   Run that from a cron job, a Fly machine scheduled task, or a Render cron service, every
   15 to 30 minutes. NWS asks that you poll no more often than every 30 seconds; AirNow
   allows 500 requests an hour.

---

## 5. Things to know before showing it to anyone

- **No PHI anywhere.** Mode A only: every panel is an aggregate estimate with its formula
  and sources attached. There are no patient records, real or synthetic.
- **The clinical content is under review.** See the open items at the top of `PROGRESS.md`,
  in particular the VHA-user share used to scale literature rates, the heat-watch trigger,
  and the empty caregiver content.
- **Times are UTC throughout**, including the "as of" control in the page header.
- **No API keys are needed for the map.** The basemap is drawn from the county boundaries
  the application serves itself, so it works offline and behind a firewall.
