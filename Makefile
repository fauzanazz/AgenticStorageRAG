# DingDong RAG - Makefile
# Run `make help` to see all available commands.

.PHONY: help dev dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend build migrate migration clean

# Default
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Development ---
dev: ## Start all services (Docker Compose)
	docker compose up --build

dev-backend: ## Start backend with hot-reload
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Start frontend dev server
	cd frontend && npm run dev

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
migrate: ## Run database migrations
	cd backend && alembic upgrade head

migration: ## Create a new migration (usage: make migration msg="add users table")
	cd backend && alembic revision --autogenerate -m "$(msg)"

# --- Build ---
build: ## Build all Docker images
	docker compose build

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
