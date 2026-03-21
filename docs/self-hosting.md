# Self-Hosting Guide

Complete guide to deploy DriveRAG on your own infrastructure.

## 1. Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | v2+ | Runs all infrastructure services |
| Node.js | 18+ | Frontend build (only needed without Docker) |
| Python | 3.12+ | Backend (only needed without Docker) |
| LLM API keys | 1 required | Anthropic (primary) and/or OpenAI (fallback) |

## 2. Clone and Configure

```bash
git clone https://github.com/your-org/openrag.git
cd openrag
cp .env.example .env
```

Edit `.env` with your values. The critical variables are:

| Variable | Required | Description |
|----------|:--------:|-------------|
| `JWT_SECRET_KEY` | Yes | Random string for signing auth tokens. Generate with: `openssl rand -hex 32` |
| `ANTHROPIC_API_KEY` | Yes* | Claude API key (primary LLM). *At least one LLM key required |
| `OPENAI_API_KEY` | Yes* | OpenAI API key (fallback LLM). *At least one LLM key required |
| `DATABASE_URL` | No | Defaults to local Docker Postgres |
| `NEO4J_URI` / `NEO4J_PASSWORD` | No | Defaults to local Docker Neo4j |
| `REDIS_URL` | No | Defaults to local Docker Redis |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | No | Only needed for Supabase file storage |

## 3. Start Services

**Option A: Full local stack (recommended)**

```bash
make dev
```

This starts all 6 services via Docker Compose:
- PostgreSQL 17 + pgvector (port 5432)
- Neo4j 5 with APOC plugin (browser: port 17474, bolt: port 17687)
- Redis 7 (port 6379)
- Backend API (port 8000)
- Background worker (same image, runs job queue)
- Frontend Next.js (port 3000)

**Option B: Supabase for database**

If you have a Supabase project for Postgres + file storage:

```bash
# Set these in .env first:
# SUPABASE_URL=https://your-project.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
# DATABASE_URL=postgresql+asyncpg://postgres:...@db.your-project.supabase.co:5432/postgres

make dev-supabase
```

This starts Neo4j + Redis + backend + worker + frontend locally, using Supabase for Postgres and file storage.

**Option C: Without Docker (manual)**

Requires PostgreSQL, Neo4j, and Redis running separately.

```bash
# Terminal 1: Backend
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Worker (processes background jobs)
cd backend && uv run python -m app.infra.worker

# Terminal 3: Frontend
cd frontend && npm install && npm run dev
```

## 4. Initialize Database

Run Alembic migrations to create tables:

```bash
# If using local Docker Postgres:
make migrate-local

# If using Supabase or external Postgres (uses DATABASE_URL from .env):
make migrate
```

## 5. Create User Accounts

```bash
make seed
```

Creates two dev accounts:
- **Admin:** `admin@dingdong.dev` / `admin123`
- **User:** `user@dingdong.dev` / `user123`

The admin account is required to trigger ingestion jobs from the UI.

## 6. Verify

Open your browser:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/api/v1 |
| API Docs (Swagger) | http://localhost:8000/api/v1/docs |
| Health Check | http://localhost:8000/api/v1/health/detailed |
| Neo4j Browser | http://localhost:17474 |

The `/health/detailed` endpoint reports the status of all infrastructure connections (Postgres, Neo4j, Redis, LLM).
