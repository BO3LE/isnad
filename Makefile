.DEFAULT_GOAL := help
SHELL := /bin/bash
VENV := source .venv/bin/activate &&

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- Docker
up: ## Start the whole stack (frontend, api, worker, redis, db)
	docker compose up --build

down: ## Stop the stack
	docker compose down

reset: ## Stop the stack and delete the database and artifacts volumes
	docker compose down -v

logs: ## Follow api and worker logs
	docker compose logs -f api worker

migrate: ## Apply migrations and seed data inside Docker
	docker compose run --rm migrate

revision: ## Create a migration: make revision m="add something"
	docker compose run --rm migrate alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------- Local (no Docker)
bootstrap: ## Create .venv with every Python component installed (editable), and install the git hooks
	scripts/bootstrap.sh
	cd frontend && npm ci
	$(VENV) pre-commit install --install-hooks

test: ## Run every component's own test suite
	$(VENV) scripts/test_all.sh
	cd frontend && npm test

lint: ## ruff + format check + import boundaries + agent shape + frontend lint
	$(VENV) ruff check . && ruff format --check . && lint-imports && python scripts/validate_manifests.py
	cd frontend && npm run lint && npm run typecheck

format: ## Auto-format Python
	$(VENV) ruff format . && ruff check --fix .

hooks: ## Install the git hooks (run once per clone)
	$(VENV) pre-commit install --install-hooks

hooks-all: ## Run every hook against the whole repo, not just staged files
	$(VENV) pre-commit run --all-files

openapi: ## Regenerate contracts/openapi.json and the frontend API types
	$(VENV) python -m api.export_openapi
	cd frontend && npm run gen:api

# ---------------------------------------------------------------- Landing page
landing: ## Rebuild landing/site/index.html from landing/index.html
	python3 landing/build-site.py

landing-check: ## Fail if landing/site/index.html is out of date
	python3 landing/build-site.py
	git diff --exit-code -- landing/site/index.html

check: lint test ## Everything CI runs, locally

.PHONY: help up down reset logs migrate revision bootstrap test lint format hooks hooks-all openapi landing landing-check check
