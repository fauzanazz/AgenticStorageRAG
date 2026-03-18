# DingDong RAG - Makefile
# Run `make help` to see all available commands.

.PHONY: help dev dev-supabase dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend build migrate migrate-local migration seed graph-schema graph-seed graph-seed-clean graph-export clean down logs ps

# Default
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Development ---
dev: ## Start full local stack (Postgres + Neo4j + Redis + backend + worker + frontend)
	docker compose --profile local up --build

dev-supabase: ## Start with Supabase DB (Neo4j + Redis + backend + worker + frontend, DB from .env)
	docker compose --profile supabase up --build

dev-backend: ## Start backend with hot-reload (no Docker)
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Start frontend dev server (no Docker)
	cd frontend && npm run dev

down: ## Stop all running services
	docker compose --profile local --profile supabase down

logs: ## Tail logs from all running services
	docker compose --profile local --profile supabase logs -f --tail=50

ps: ## Show running service status
	docker compose --profile local --profile supabase ps

# --- Testing ---
test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests with coverage
	cd backend && python -m pytest --cov=app --cov-report=term-missing

test-frontend: ## Run frontend tests
	cd frontend && npm run test -- --run

# --- Linting ---
lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Lint + format + type-check backend
	cd backend && ruff check app/ && ruff format --check app/ && mypy app/

lint-frontend: ## Lint frontend
	cd frontend && npm run lint

# --- Database ---
migrate: ## Run migrations against Supabase (uses DATABASE_URL from .env)
	cd backend && set -a && source ../.env && set +a && uv run alembic upgrade head

migrate-local: ## Run migrations against local Docker Postgres
	cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dingdong_rag uv run alembic upgrade head

migration: ## Create a new migration (usage: make migration msg="add users table")
	cd backend && set -a && source ../.env && set +a && uv run alembic revision --autogenerate -m "$(msg)"

seed: ## Seed dev accounts (admin@dingdong.dev / admin123, user@dingdong.dev / user123)
	cd backend && python -m app.scripts.seed

# --- Knowledge Graph ---
graph-schema: ## Apply Neo4j indexes and constraints (idempotent)
	cd backend && python -m app.scripts.graph_schema

graph-seed: ## Seed Neo4j + PG from local graph files (idempotent merge/upsert)
	cd backend && python -m app.scripts.graph_import

graph-seed-clean: ## Wipe Neo4j + PG knowledge tables and re-seed from local graph files
	cd backend && python -m app.scripts.graph_import --clean

graph-export: ## Export current Neo4j graph to versioned JSONL seed files
	cd backend && python -m app.scripts.graph_export

# --- Build ---
build: ## Build all Docker images
	docker compose --profile local build

build-backend: ## Build backend Docker image
	docker build -t dingdong-rag-backend ./backend

build-frontend: ## Build frontend Docker image
	docker build -t dingdong-rag-frontend ./frontend

# --- Clean ---
clean: ## Remove all build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/dist backend/build frontend/out
