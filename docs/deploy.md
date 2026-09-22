# Running and hosting the demo

Two ways to run it: **locally** with `uv` (best for development) or **as a container**
(best for showing it to someone else). Both default to replay mode, which needs no API key
and no network, because the reference data and the five replay scenarios are committed to
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
2. `scripts/ingest.py --mode replay` — the five replay scenarios (15,648 events)
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

### Developing: serve your working tree, not a container

A container is a snapshot of the code at the time its image was built. If one is running
on :8000, for example the `mee` container started with `--restart unless-stopped`, it comes
back whenever Docker starts. It keeps answering on :8000 with the old code, and changes in
your working tree never show up. Check with `docker ps`.

To see your edits, serve the working tree with `make serve`. It runs uvicorn with
`--reload`, so the server restarts whenever you save a Python file. After editing JS or
CSS, hard-refresh the browser (Cmd+Shift+R).

**Option A: stop the container and use :8000.**

```sh
docker stop mee                                # stays stopped, even across Docker restarts
DATABASE_URL=sqlite:///demo.db make serve      # the database `make demo` already built
docker start mee                               # later, to bring the snapshot back
```

**Option B: keep the container on :8000 and run the working tree beside it.**

```sh
DATABASE_URL=sqlite:///demo.db make serve PORT=8001
```

Then :8000 is the snapshot and :8001 is your code. `make demo PORT=8001` works the same
way.

Notes:

- **Name the database on the command line.** `make serve` reads `DATABASE_URL` from `.env`
  when you don't. If `.env` points at the compose Postgres, run `make db-up` first. A
  variable set on the command line takes precedence over `.env`.
- **When to re-run the pipeline.** You don't need to rebuild the database for UI or API
  changes. After changing cards, the profile, the engine, the denominators or the fixtures,
  re-run `DATABASE_URL=sqlite:///demo.db make load ingest match` (or `make demo`), because
  the action items are stored, not computed per request.
- **Updating the container** to the current code takes a rebuild and a replacement:

  ```sh
  docker build -t med-extreme-events:demo .
  docker rm -f mee
  docker run -d --name mee --restart unless-stopped -p 8000:8000 \
    -e NWS_USER_AGENT="med-extreme-events (contact: you@example.com)" med-extreme-events:demo
  ```

  The image bakes only the replays. Live events are not in the image: the app refreshes
  them itself at startup and then hourly (`LIVE_REFRESH_MINUTES`, default 60 in the image;
  `0` turns it off), so a replaced container repopulates its live view within about a
  minute. Watch it with `docker logs -f mee | grep "live refresh"`.

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

Open <http://localhost:8000>. The container runs the code as it was when you built the
image, so rebuild after pulling or editing (see "Developing" in §1). The image is roughly 400 MB and starts in a couple of seconds; most of
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

### Render from GitHub — the recommended public deployment

`render.yaml` in the repository root is a Render blueprint: a Docker web service on the free
plan, health-checked at `/health`, with `autoDeployTrigger: checksPass`. Every push to `main`
runs the GitHub `ci` workflow (lint + the full test suite, goldens included); Render rebuilds
and redeploys only when those checks pass, so a broken commit never reaches the public URL.

One-time setup (about five minutes, no CLI):

1. Sign in at [render.com](https://render.com) with the GitHub account that owns the repo.
2. **New → Blueprint**, choose `shlyakhter1/med-extreme-events`, and **Apply**. Render reads
   `render.yaml`, builds the image (the build bakes the replay database, about a minute) and
   serves it at `https://med-extreme-events.onrender.com` (or a suffixed name if taken).
3. Nothing else: from then on, `git push` to `main` is the deploy.

Notes:

- The free instance sleeps after about 15 minutes idle; the first request after that takes
  roughly a minute to wake it. The paid Starter plan (change `plan:` in `render.yaml`) stays
  warm.
- The site is public and has no login. The data is aggregate (no PHI), but the acknowledge
  and complete buttons are open to anyone; their changes are discarded on every redeploy,
  because the database is rebuilt into each image.
- Live events refresh inside the app at startup and hourly (`LIVE_REFRESH_MINUTES` in
  `render.yaml`). They are not persistent: a redeploy or a wake from sleep starts from the
  image and refills within about a minute. NWS, the IEM archive, OpenFEMA and NOAA smoke need
  no key; EAGLE-I is skipped unless `EAGLEI_TOKEN` or `EAGLEI_FEATURE_URL` is set, and AirNow
  unless `AIRNOW_API_KEY` is (set secrets in the Render dashboard, not in `render.yaml`).

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
Live mode pulls current NWS alerts (plus the two-week IEM archive backfill), FEMA
declarations, NOAA smoke polygons, EAGLE-I county outages (`EAGLEI_TOKEN` for FEMA's
partner layer, or a public mirror via `EAGLEI_FEATURE_URL`) and, with a key, AirNow, so it
needs writable storage and outbound network access.

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
