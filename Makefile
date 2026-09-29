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

measure-video: ## Measure video render cost in the worker image under prod limits: make measure-video args="--parallel 2"
	docker build -q -f worker/Dockerfile --target dev -t isnad-worker-measure .
	docker run --rm --cpus $(or $(CPUS),2) --memory $(or $(MEM),4g) -v "$(CURDIR)/scripts:/app/scripts:ro" \
	  --entrypoint bash isnad-worker-measure -c "pip install -q -c constraints.txt psutil && python scripts/measure_video_worker.py $(args)"

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

test-integration: ## Run tests/integration (full run lifecycle) against the Docker PostgreSQL
	docker compose up -d --wait db
	$(VENV) INTEGRATION_DATABASE_URL=$${INTEGRATION_DATABASE_URL:-postgresql://postgres:postgres@localhost:$${DB_HOST_PORT:-5433}/gp} python -m pytest tests/integration -q

reliability: ## W10: drive 60 runs through the real stack and write docs/metrics/reliability.md (needs `make up` running)
	docker compose up -d --build db redis migrate api worker
	$(VENV) python scripts/reliability_campaign.py both --runs $(or $(RUNS),60) --concurrency $(or $(CONCURRENCY),2)

latency: ## W9: measure p95 API latency idle vs during a 1080p video render, writes docs/metrics/api-latency.md
	docker compose up -d --build db redis migrate api
	docker build -q -f worker/Dockerfile --target prod -t isnad-worker-prod .
	docker run -d --rm --name isnad-worker-latency --network isnad_default --network-alias worker \
	  --cpus 2 --memory 4g \
	  -e DATABASE_URL=postgresql://postgres:postgres@db:5432/gp -e REDIS_URL=redis://redis:6379/0 \
	  -e STORAGE_ROOT=/data/artifacts -e PUBLIC_FILES_URL=http://localhost:8000/files \
	  -v isnad_artifacts:/data/artifacts isnad-worker-prod
	$(VENV) python scripts/measure_api_latency.py both --duration $(or $(DURATION),30) \
	  --concurrency $(or $(CONCURRENCY),8) --videos $(or $(VIDEOS),2)
	docker stop isnad-worker-latency

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

# ---------------------------------------------------------------- CD/DVD (W12)
dist: ## Build dist/isnad-cd/ + dist/isnad-cd.zip: source + SETUP.md + TOOLS.md + report/ placeholder
	$(VENV) python scripts/make_dist.py

fresh-machine-test: ## W11: clone HEAD into a temp dir, docker compose up --build, smoke test, teardown
	scripts/fresh_machine_test.sh

# ---------------------------------------------------------------- Landing page
landing: ## Rebuild landing/site/index.html from landing/index.html
	python3 landing/build-site.py

landing-check: ## Fail if landing/site/index.html is out of date
	python3 landing/build-site.py
	git diff --exit-code -- landing/site/index.html

check: lint test ## Everything CI runs, locally

.PHONY: help up down reset logs measure-video migrate revision bootstrap test test-integration reliability latency lint format hooks hooks-all openapi dist fresh-machine-test landing landing-check check
