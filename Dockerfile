# Self-contained demo image: the build bakes a SQLite database from the reference data and
# replay scenarios committed to this repo, so the running container needs no API key, no
# Postgres and no network access. Live mode is opt-in at runtime (see docs/deploy.md).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/src

WORKDIR /app

# Dependencies first so source edits do not invalidate the install layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY cards/ ./cards/
COPY profiles/ ./profiles/
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/
# The carbon table is display data read at runtime (docs/carbon-footprint.md has the methods).
COPY docs/carbon.yaml ./docs/carbon.yaml

# Build the demo database at image build time: facilities + catchments, the five replay
# scenarios, and the action items the engine derives from them.
ENV DATABASE_URL=sqlite:////app/demo.db
RUN python scripts/load_reference.py \
 && python scripts/ingest.py --mode replay \
 && python scripts/match.py --mode replay

EXPOSE 8000
ENV PORT=8000
# Live events are not baked into the image; the app refreshes them itself at startup and then
# hourly (src/xevents/live_refresh.py). NWS requires a contact string; the public repository
# is that contact. Override either at run time; LIVE_REFRESH_MINUTES=0 turns refresh off.
ENV LIVE_REFRESH_MINUTES=60 \
    NWS_USER_AGENT="med-extreme-events demo (https://github.com/shlyakhter1/med-extreme-events)"
# Render and Railway inject $PORT; Fly uses the internal_port in fly.toml.
CMD ["sh", "-c", "exec uvicorn xevents.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
