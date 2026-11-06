# BVT MDM: developer entry points. Run `make help`.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE := docker compose
API := cd api &&
WEB := cd web &&
E2E := cd e2e &&
E2E_COMPOSE := $(COMPOSE) -f docker-compose.yml -f docker-compose.e2e.yml
# Git Bash on Windows rewrites "/repo"-style arguments; turn that off for docker.
export MSYS_NO_PATHCONV := 1

.PHONY: help
help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-16s %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------
.PHONY: install secrets hooks
install: hooks ## Install API (uv), web + e2e (npm, Playwright Chromium) and git hooks
	$(API) uv sync
	$(WEB) npm ci --no-fund
	$(E2E) npm ci --no-fund && npx playwright install chromium

hooks: ## Enable the versioned git hooks (gitleaks pre-commit)
	git config core.hooksPath .githooks

secrets: ## Print fresh random values for .env
	@python -c "import secrets; \
	print('POSTGRES_SUPERUSER_PASSWORD=' + secrets.token_urlsafe(24)); \
	print('MDM_MIGRATOR_PASSWORD=' + secrets.token_urlsafe(24)); \
	print('MDM_APP_PASSWORD=' + secrets.token_urlsafe(24)); \
	print('MDM_READONLY_PASSWORD=' + secrets.token_urlsafe(24))"

# --- Database ----------------------------------------------------------------
.PHONY: db-up db-down db-bootstrap migrate db-psql
db-up: ## Start the MDM Postgres container (port 54330)
	$(COMPOSE) --profile db up -d db

db-down: ## Stop the MDM Postgres container (data volume is kept)
	$(COMPOSE) --profile db stop db

db-bootstrap: ## Re-run role/DB bootstrap (idempotent; rotates role passwords from .env)
	$(COMPOSE) --profile db exec db sh /docker-entrypoint-initdb.d/10-bootstrap.sh

migrate: ## Apply Alembic migrations (as mdm_migrator)
	$(API) uv run alembic upgrade head

db-psql: ## Open psql in the db container as superuser
	$(COMPOSE) --profile db exec db psql -U postgres -d mdm

# --- Run ---------------------------------------------------------------------
.PHONY: up down
up: ## Build and run everything -> http://localhost:8080
	$(COMPOSE) --profile db up -d --build db
	$(COMPOSE) --profile tools run --rm --build migrate
	$(COMPOSE) up -d --build api web

down: ## Stop all containers (volumes kept)
	$(COMPOSE) --profile db --profile tools down

# --- Quality -----------------------------------------------------------------
.PHONY: test e2e lint format typecheck audit check
test: ## Run the API test suite (uses the mdm_test database)
	$(API) uv run pytest

lint: ## ruff + eslint
	$(API) uv run ruff check . && uv run ruff format --check .
	$(WEB) npm run -s lint

format: ## Auto-format Python
	$(API) uv run ruff format . && uv run ruff check --fix .

typecheck: ## mypy (strict) + tsc (web and e2e)
	$(API) uv run mypy app tests alembic/env.py alembic/alembic_helpers.py scripts
	$(WEB) npm run -s typecheck
	$(E2E) npx tsc --noEmit

audit: ## pip-audit, bandit, npm audit, gitleaks
	$(API) uv run pip-audit --progress-spinner off
	$(API) uv run python -m bandit -q -c pyproject.toml -r app alembic
	$(WEB) npm audit --audit-level=moderate
	$(E2E) npm audit --audit-level=moderate
	sh scripts/check_images.sh
	sh scripts/gitleaks.sh tree
	@if git rev-parse --verify -q HEAD >/dev/null; then sh scripts/gitleaks.sh history; fi

e2e: ## Playwright in headless Chromium against the Docker stack (mock Google, DB mdm_e2e)
	$(E2E_COMPOSE) --profile db up -d --build db
	$(E2E_COMPOSE) --profile tools run --rm --build migrate
	$(E2E_COMPOSE) up -d --build --wait api web mock-oidc
	@status=0; ( $(E2E) npx playwright test ) || status=$$?; 	  echo "e2e: restoring the normal stack"; 	  $(E2E_COMPOSE) rm -sf mock-oidc >/dev/null; 	  $(COMPOSE) up -d --wait api web >/dev/null; 	  exit $$status

check: lint typecheck test audit e2e ## Everything a phase must pass
