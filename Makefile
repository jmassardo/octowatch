.PHONY: help dev build test test-backend test-frontend lint lint-backend lint-frontend format migrate gen-env gen-env-local dev-infra dev-local dev-backend dev-frontend clean logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

dev: ## Start the full development stack
	docker compose up -d

build: ## Build all Docker images
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

gen-env: ## Generate .env from template (Docker hostnames)
	python scripts/gen_env.py

gen-env-local: ## Generate .env with localhost hostnames for local dev
	@echo "NOTE: If the DB volume already exists with different credentials, run 'docker compose down -v' first."
	python scripts/gen_env.py --local

dev-infra: ## Start only infrastructure services (db, valkey, minio) for local dev
	docker compose up -d db valkey minio minio-setup

dev-local: dev-infra ## Start backend + frontend locally (requires dev-infra)
	@echo "Infrastructure started. Run in separate terminals:"
	@echo "  cd backend && set -a && . ../.env && set +a && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
	@echo "  cd frontend && npm run dev"

dev-backend: ## Start backend locally with auto-reload
	cd backend && set -a && . ../.env && set +a && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Start frontend dev server
	cd frontend && npm run dev

clean: ## Stop and remove all containers and volumes
	docker compose down -v

logs: ## Tail logs for all services
	docker compose logs -f --tail=50
