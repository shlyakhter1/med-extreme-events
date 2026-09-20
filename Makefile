# VA extreme-event demo — entry points. All Python runs through `uv run` (no venv activation needed).
UV ?= uv
SKILLS_REPO ?= ../../nyc2026-dataset
# If a .env exists at the repo root, every `uv run` below loads it (dotenv format).
ENV_FILE := $(wildcard .env)
RUN = $(UV) run $(if $(ENV_FILE),--env-file $(ENV_FILE),)

.PHONY: help install lint fmt test schema skills skills-check db-up db-down reference load serve ingest match scenarios demo clean

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

reference: ## rebuild cached reference data (county boundaries, ZIP↔county; facilities needs VA_FACILITIES_API_KEY)
	$(RUN) python scripts/build_county_boundaries.py
	$(RUN) python scripts/build_nws_zones.py
	$(RUN) python scripts/build_ct_crosswalk.py
	$(RUN) python scripts/build_zip_county.py
	$(RUN) python scripts/build_facilities.py

load: ## load cached reference data into DATABASE_URL (SQLite fallback) with county/VISN attribution
	$(RUN) python scripts/load_reference.py

serve: ## run the API locally
	$(RUN) uvicorn xevents.api:app --reload --port 8000

ingest: ## load events for EVENT_MODE=replay|live (default replay: all fixture scenarios)
	$(RUN) python scripts/ingest.py

match: ## run the matching engine over stored events (EVENT_MODE=replay|live) → action items
	$(RUN) python scripts/match.py

scenarios: ## rebuild fixtures/events/*/events.json from their raw archived sources
	$(RUN) python fixtures/events/heat_dome_2021/build.py
	$(RUN) python fixtures/events/ian_2022/build.py
	$(RUN) python fixtures/events/smoke_nyc_2023/build.py

demo: ## (M5) fresh DB, reference data, cards, heat-dome replay, dashboard
	@echo "demo: not implemented until M5" && exit 1

clean: ## remove caches
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
