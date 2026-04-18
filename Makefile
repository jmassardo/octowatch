.PHONY: help dev dev-up dev-down dev-logs dev-build build test test-backend test-frontend lint lint-backend lint-frontend format migrate gen-env clean

DEV_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml

# Auto-detect Codespaces and set APP_BASE_URL for OAuth callbacks
ifdef CODESPACE_NAME
export APP_BASE_URL ?= https://$(CODESPACE_NAME)-5173.$(GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN)
endif

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

dev: ## Start the full production-like stack (pre-built images)
	docker compose up -d

dev-up: ## Start dev stack with hot-reload (no image rebuilds needed)
	$(DEV_COMPOSE) up -d

dev-down: ## Stop the dev stack
	$(DEV_COMPOSE) down

dev-logs: ## Tail dev stack logs
	$(DEV_COMPOSE) logs -f --tail=50

dev-build: ## Build dev images (only needed once or after Dockerfile changes)
	$(DEV_COMPOSE) build

build: ## Build all production Docker images
	docker compose build

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests with coverage
	cd backend && pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=60

test-frontend: ## Run frontend tests
	cd frontend && npm test

lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Lint and type-check backend
	cd backend && ruff check . && ruff format --check .

lint-frontend: ## Lint and format-check frontend
cd frontend && npm run lint && npm run format:check

format: ## Auto-format all code
	cd backend && ruff format .
	cd frontend && npm run format

migrate: ## Run database migrations
	cd backend && alembic upgrade head

gen-env: ## Generate .env from template
	python scripts/gen_env.py

clean: ## Stop and remove all containers and volumes
	docker compose down -v

logs: ## Tail logs for all services
	docker compose logs -f --tail=50

seed-data: ## Generate realistic sample audit data (30 days)
	cd backend && python scripts/seed_data.py
