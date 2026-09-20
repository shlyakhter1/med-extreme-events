# VA extreme-event demo — entry points. All Python runs through `uv run` (no venv activation needed).
UV ?= uv
SKILLS_REPO ?= ../../nyc2026-dataset

.PHONY: help install lint fmt test schema skills skills-check db-up db-down ingest demo clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

install: ## create the venv and install runtime + dev deps
	$(UV) sync

lint: ## ruff (lint + format check) and mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

fmt: ## auto-format and auto-fix lint
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

test: ## run the test suite (network-marked tests skipped unless RUN_NETWORK_TESTS=1)
	$(UV) run pytest

schema: ## regenerate cards/card.schema.json from the Pydantic models
	$(UV) run python scripts/export_card_schema.py

skills: ## (re)link data-source skills from the sibling skills repo into .claude/skills
	SKILLS_REPO=$(SKILLS_REPO) $(UV) run python scripts/link_skills.py

skills-check: ## verify every linked skill resolves
	SKILLS_REPO=$(SKILLS_REPO) $(UV) run python scripts/link_skills.py --check

db-up: ## start postgres+postgis via docker compose
	docker compose up -d db

db-down: ## stop the database
	docker compose down

ingest: ## (M2) load events for EVENT_MODE=replay|live
	@echo "ingest: not implemented until M2" && exit 1

demo: ## (M5) fresh DB, reference data, cards, heat-dome replay, dashboard
	@echo "demo: not implemented until M5" && exit 1

clean: ## remove caches
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
