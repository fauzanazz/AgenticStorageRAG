# Development

## Project Structure

```
driverag/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan
│   │   ├── config.py            # Pydantic Settings
│   │   ├── dependencies.py      # DI container
│   │   ├── infra/               # Database, Neo4j, Redis, LLM, worker
│   │   └── domain/              # Domain-driven modules
│   │       ├── auth/            # JWT auth + user management
│   │       ├── documents/       # Upload, processing, chunking
│   │       │   └── processors/  # PDF, DOCX (extensible)
│   │       ├── knowledge/       # Graph + vector + hybrid retrieval
│   │       ├── agents/          # RAG agent + tools
│   │       └── ingestion/       # Google Drive sync
│   ├── alembic/                 # DB migrations
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── app/                 # App Router pages
│       │   ├── (auth)/          # Login, register
│       │   └── (dashboard)/     # Chat, documents, knowledge, settings
│       ├── components/          # UI components (shadcn/ui + custom)
│       ├── hooks/               # use-auth, use-chat, use-documents, etc.
│       └── lib/                 # Utilities
├── contracts/
│   └── openapi.yaml             # API contract (source of truth)
├── docker-compose.yml           # 2 profiles: local, supabase
└── Makefile                     # Dev commands (run `make help`)
```

## Commands

```bash
make help              # Show all commands

# Dev
make dev               # Full local stack
make dev-supabase      # With Supabase DB
make dev-backend       # Backend only (no Docker)
make dev-frontend      # Frontend only (no Docker)

# Test
make test              # All tests
make test-backend      # Backend (pytest + coverage)
make test-frontend     # Frontend (vitest)

# Lint
make lint              # All linters
make lint-backend      # ruff + mypy
make lint-frontend     # eslint

# Database
make migrate           # Run migrations (production)
make migrate-local     # Run migrations (local Docker)
make migration msg="description"  # Create new migration
make seed              # Seed dev accounts

# Ops
make build             # Build Docker images
make down              # Stop services
make logs              # Tail logs
make clean             # Remove caches + artifacts
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/detailed` | Service status (DB, Neo4j, Redis, LLM) |
| `POST` | `/auth/register` | Register user |
| `POST` | `/auth/login` | Login (returns JWT) |
| `POST` | `/auth/refresh` | Refresh access token |
| `GET` | `/auth/me` | Current user info |

Full contract: [`contracts/openapi.yaml`](../contracts/openapi.yaml)

## Environment Variables

See [`.env.example`](../.env.example) for the full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection (asyncpg) |
| `NEO4J_URI` / `NEO4J_PASSWORD` | Neo4j graph database |
| `REDIS_URL` | Job queue |
| `ANTHROPIC_API_KEY` | Primary LLM |
| `OPENAI_API_KEY` | Fallback LLM |
| `JWT_SECRET_KEY` | Auth token signing |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase (if using) |
