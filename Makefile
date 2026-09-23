# VA extreme-event demo — entry points. All Python runs through `uv run` (no venv activation needed).
UV ?= uv
SKILLS_REPO ?= ../../nyc2026-dataset
PORT ?= 8000
# If a .env exists at the repo root, every `uv run` below loads it (dotenv format).
ENV_FILE := $(wildcard .env)
RUN = $(UV) run $(if $(ENV_FILE),--env-file $(ENV_FILE),)

.PHONY: help install lint fmt test schema skills skills-check db-up db-down reference load serve ingest match scenarios demo container clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

install: ## create the venv and install runtime + dev deps
	$(UV) sync

lint: ## ruff (lint + format check) and mypy
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

fmt: ## auto-format and auto-fix lint
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

test: ## run the test suite (network-marked tests skipped unless RUN_NETWORK_TESTS=1)
	$(RUN) pytest

schema: ## regenerate cards/card.schema.json from the Pydantic models
	$(RUN) python scripts/export_card_schema.py

skills: ## (re)link data-source skills from the sibling skills repo into .claude/skills
	SKILLS_REPO=$(SKILLS_REPO) $(RUN) python scripts/link_skills.py

skills-check: ## verify every linked skill resolves
	SKILLS_REPO=$(SKILLS_REPO) $(RUN) python scripts/link_skills.py --check

db-up: ## start postgres+postgis via docker compose
	docker compose up -d db

db-down: ## stop the database
	docker compose down

reference: ## rebuild all cached reference data (boundaries, zones, crosswalks, PLACES, VetPop, EAGLE-I customers, emPOWER; facilities needs VA_FACILITIES_API_KEY)
	$(RUN) python scripts/build_county_boundaries.py
	$(RUN) python scripts/build_state_boundaries.py
	$(RUN) python scripts/build_countries.py
	$(RUN) python scripts/build_nws_zones.py
	$(RUN) python scripts/build_ct_crosswalk.py
	$(RUN) python scripts/build_zip_county.py
	$(RUN) python scripts/build_places.py
	$(RUN) python scripts/build_vetpop.py
	$(RUN) python scripts/build_eaglei_customers.py
	$(RUN) python scripts/build_empower.py
	$(RUN) python scripts/build_facilities.py

load: ## load cached reference data into DATABASE_URL (SQLite fallback) with county/VISN attribution
	$(RUN) python scripts/load_reference.py

serve: ## run the API locally from the working tree, reloading on change (PORT=8000)
	$(RUN) uvicorn xevents.api:app --reload --port $(PORT)

ingest: ## load events for EVENT_MODE=replay|live (default replay: all fixture scenarios)
	$(RUN) python scripts/ingest.py

match: ## run the matching engine over stored events (EVENT_MODE=replay|live) → action items
	$(RUN) python scripts/match.py

scenarios: ## rebuild fixtures/events/*/events.json from their raw archived sources
	$(RUN) python fixtures/events/heat_dome_2021/build.py
	$(RUN) python fixtures/events/ian_2022/build.py
	$(RUN) python fixtures/events/smoke_nyc_2023/build.py
	$(RUN) python fixtures/events/uri_2021/build.py
	$(RUN) python fixtures/events/smoke_canada_2026/build.py

DEMO_DB ?= sqlite:///demo.db
# Page `make demo` opens: empty = live view; e.g. SCENARIO=heat_dome_2021 for a replay.
SCENARIO ?=
DEMO_URL = http://localhost:$(PORT)/$(if $(SCENARIO),?scenario=$(SCENARIO),)

demo: ## (SCENARIO=<id> to open a replay) fresh SQLite DB → reference data + catchments → replay scenarios → action items → dashboard
	rm -f demo.db
	DATABASE_URL=$(DEMO_DB) $(RUN) python scripts/load_reference.py
	DATABASE_URL=$(DEMO_DB) $(RUN) python scripts/ingest.py --mode replay
	DATABASE_URL=$(DEMO_DB) $(RUN) python scripts/match.py --mode replay
	@echo "open $(DEMO_URL)  (replays: /?scenario=heat_dome_2021, /playback)"
	-open "$(DEMO_URL)" 2>/dev/null || true
	DATABASE_URL=$(DEMO_DB) $(RUN) uvicorn xevents.api:app --port $(PORT)

container: ## rebuild the local demo image and replace the `mee` container on :8000 (code is baked in; restart is not enough)
	docker build -t med-extreme-events:demo .
	docker rm -f mee 2>/dev/null || true
	docker run -d --name mee --restart unless-stopped -p 8000:8000 med-extreme-events:demo
	@echo "mee rebuilt: http://localhost:8000 (live data refills in a few minutes)"

clean: ## remove caches
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
