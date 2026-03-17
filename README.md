# DingDong RAG

An agentic Knowledge Graph RAG application that ingests documents into a hybrid retrieval system (Neo4j graph + pgvector), with an autonomous AI agent that reasons over the knowledge to answer queries through a mobile-first web interface.

<img src="scorecard.png" width="100%">

## Architecture

```
Frontend (Next.js 16)          Backend (FastAPI)              Infrastructure
┌──────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  App Router      │────▶│  REST / WebSocket    │────▶│  PostgreSQL +    │
│  shadcn/ui       │     │  Domain modules:     │     │  pgvector        │
│  Tailwind CSS 4  │     │   auth, documents,   │     │  Neo4j 5         │
│  TypeScript 5    │     │   knowledge, agents, │     │  Redis 7         │
└──────────────────┘     │   ingestion          │     │  Supabase Storage│
                         │  Background worker   │     └──────────────────┘
                         └──────────────────────┘
```

**Two-tier knowledge:**
- **Base KG** -- Permanent knowledge ingested from Google Drive via agent swarm
- **User uploads** -- PDF/DOCX files with 7-day TTL, auto-extracted into graph + vectors

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16, TypeScript 5 (strict), Tailwind CSS 4, shadcn/ui |
| Backend | FastAPI, Python 3.12+, SQLAlchemy 2.0 (async), Pydantic |
| Database | PostgreSQL 17 + pgvector, Neo4j 5, Redis 7 |
| AI | LangChain + LiteLLM, Claude Sonnet 4 (primary), GPT-4o (fallback) |
| Storage | Supabase Storage (uploads), Google Drive (base KG source) |
| Infra | Docker Compose, Vercel (frontend), VPS (backend) |

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Node.js 18+ with `pnpm`
- Python 3.12+ with `uv`

### Setup

```bash
cp .env.example .env   # Edit with your API keys

# Full local stack (Postgres + Neo4j + Redis + backend + worker + frontend)
make dev

# Seed dev accounts (admin@dingdong.dev / admin123, user@dingdong.dev / user123)
make seed
```

The app will be available at:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000/api/v1
- **API Docs:** http://localhost:8000/api/v1/docs
- **Neo4j Browser:** http://localhost:17474

### Alternative: Supabase for DB

```bash
# Set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL in .env
make dev-supabase
```

### Without Docker

```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Worker
cd backend && python -m app.infra.worker

# Terminal 3: Frontend
cd frontend && pnpm dev
```

## Project Structure

```
dingdong-rag/
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

## Development

### Commands

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

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/detailed` | Service status (DB, Neo4j, Redis, LLM) |
| `POST` | `/auth/register` | Register user |
| `POST` | `/auth/login` | Login (returns JWT) |
| `POST` | `/auth/refresh` | Refresh access token |
| `GET` | `/auth/me` | Current user info |

Full contract: [`contracts/openapi.yaml`](contracts/openapi.yaml)

### Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection (asyncpg) |
| `NEO4J_URI` / `NEO4J_PASSWORD` | Neo4j graph database |
| `REDIS_URL` | Job queue |
| `ANTHROPIC_API_KEY` | Primary LLM |
| `OPENAI_API_KEY` | Fallback LLM |
| `JWT_SECRET_KEY` | Auth token signing |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase (if using) |

## Self-Hosting Guide

Complete guide to deploy DingDong RAG on your own infrastructure.

### 1. Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Docker + Docker Compose | v2+ | Runs all infrastructure services |
| Node.js | 18+ | Frontend build (only needed without Docker) |
| Python | 3.12+ | Backend (only needed without Docker) |
| LLM API keys | 1 required | Anthropic (primary) and/or OpenAI (fallback) |

### 2. Clone and Configure

```bash
git clone https://github.com/your-org/dingdong-rag.git
cd dingdong-rag
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

### 3. Start Services

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

### 4. Initialize Database

Run Alembic migrations to create tables:

```bash
# If using local Docker Postgres:
make migrate-local

# If using Supabase or external Postgres (uses DATABASE_URL from .env):
make migrate
```

### 5. Create User Accounts

```bash
make seed
```

Creates two dev accounts:
- **Admin:** `admin@dingdong.dev` / `admin123`
- **User:** `user@dingdong.dev` / `user123`

The admin account is required to trigger ingestion jobs from the UI.

### 6. Verify

Open your browser:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/api/v1 |
| API Docs (Swagger) | http://localhost:8000/api/v1/docs |
| Health Check | http://localhost:8000/api/v1/health/detailed |
| Neo4j Browser | http://localhost:17474 |

The `/health/detailed` endpoint reports the status of all infrastructure connections (Postgres, Neo4j, Redis, LLM).

---

## Self-Seeding Guide

DingDong RAG has a two-tier knowledge architecture. This section covers how to populate both tiers.

### Tier 1: Base Knowledge Graph (from Google Drive)

The base KG is permanent knowledge ingested from a Google Drive folder. Files are processed by an agent swarm that extracts entities, relationships, and embeddings.

#### Step 1: Set Up Google Drive Access

You have two authentication options:

**Option A: Service Account (recommended for production)**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Enable the **Google Drive API** (APIs & Services > Library)
3. Create a Service Account (IAM & Admin > Service Accounts)
4. Click **Keys > Add Key > Create new key > JSON** -- downloads a key file
5. Share your Drive folder with the Service Account email (found in the JSON as `client_email`) as **Viewer**
6. Set in `.env`:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
   ```
   Or for Docker/CI, paste the JSON inline:
   ```
   GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
   ```

**Option B: OAuth2 with your personal Google account (no folder sharing needed)**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) > APIs & Services > OAuth consent screen
2. Select **External**, fill in app name and emails, add yourself as a test user
3. Go to **Credentials** > Create Credentials > **OAuth client ID** > Application type: **Desktop app**
4. Copy the Client ID and Client Secret into `.env`:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-your-secret
   ```
5. Run the helper script to get a refresh token:
   ```bash
   cd backend && uv run python -m app.scripts.google_auth
   ```
   This opens your browser for Google login. Paste the printed token into `.env`:
   ```
   GOOGLE_REFRESH_TOKEN=1//0eXXXXXXXXXXXXX
   ```

Optionally set `GOOGLE_DRIVE_FOLDER_ID` in `.env` to restrict ingestion to a specific folder (the folder ID is the last segment of its Drive URL).

#### Step 2: Trigger Ingestion

**From the UI (recommended):**

1. Log in as the admin account (`admin@dingdong.dev`)
2. Navigate to the Admin panel in the sidebar
3. Click **Trigger Ingestion**
4. The swarm scans the Drive folder, downloads PDF/DOCX/Google Docs files, extracts entities and relationships, and builds the knowledge graph

**From the API:**

```bash
curl -X POST http://localhost:8000/api/v1/ingestion/trigger \
  -H "Authorization: Bearer <admin-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"folder_id": "optional-specific-folder-id", "force": false}'
```

Set `"force": true` to re-ingest files that were already processed.

The ingestion pipeline:
1. Authenticates with Google Drive
2. Scans for PDF, DOCX, and Google Docs files
3. Filters out already-ingested files (deduplication by Drive file ID)
4. Downloads and processes files in parallel (5 concurrent workers)
5. Extracts text, chunks documents, generates embeddings
6. Builds the knowledge graph (entities + relationships in Neo4j + PostgreSQL)
7. Detects updated files (by `modifiedTime`) and re-processes them automatically

#### Step 3: Export the Graph (Optional)

Once your knowledge graph is built, you can export it to versioned JSONL seed files. This lets you ship a pre-built graph with the repo so others can self-host without needing Google Drive access.

```bash
make graph-export
```

This creates files in `backend/graph_seed/`:
```
graph_seed/
├── manifest.json                     # Version, checksums, file listing
├── schema/
│   └── constraints.cypher            # Neo4j indexes and constraints
├── entities/
│   ├── Person.jsonl                  # One JSONL file per entity type
│   ├── Organization.jsonl
│   └── ...
└── relationships/
    ├── WORKS_AT.jsonl                # One JSONL file per relationship type
    ├── RELATED_TO.jsonl
    └── ...
```

Files larger than 40MB are automatically sharded (e.g., `Person_001.jsonl`, `Person_002.jsonl`).

### Tier 1 (alternative): Seed from Local Files

If the repo already has exported graph seed files in `backend/graph_seed/`, you can populate the knowledge graph without Google Drive:

**Auto-seed on startup:**

The backend automatically seeds the graph from local files when Neo4j is empty and `graph_seed/manifest.json` exists. Just start the app -- it happens automatically during the lifespan startup.

**Manual seed:**

```bash
# Idempotent merge/upsert (safe to run multiple times)
make graph-seed

# Or wipe and re-import from scratch
make graph-seed-clean
```

**Apply schema only (indexes and constraints):**

```bash
make graph-schema
```

### Tier 2: User Uploads

Users can upload PDF and DOCX files through the web UI. These are:
- Stored in Supabase Storage (or local if not configured) with a **7-day TTL**
- Processed into text chunks and embeddings
- Added to the knowledge graph with source metadata
- Automatically cleaned up when they expire

No additional setup needed beyond the base configuration. Users upload files from the Documents page in the dashboard.

### Knowledge Graph Commands Reference

```bash
make graph-schema       # Apply Neo4j indexes and constraints (idempotent)
make graph-seed         # Import from local JSONL files (idempotent merge)
make graph-seed-clean   # Wipe graph + re-import from local files
make graph-export       # Export current graph to versioned JSONL files
```

---

## Production Deployment

### Backend (VPS/Cloud)

1. Build the production Docker image:
   ```bash
   make build-backend
   ```
2. The production image uses a non-root user, runs 4 Uvicorn workers, and includes a health check
3. Deploy with your `.env` file (or environment variables) pointing to your production databases
4. Run migrations against production Postgres:
   ```bash
   make migrate
   ```

### Frontend (Vercel or Docker)

**Vercel:**
- Set `NEXT_PUBLIC_API_URL` to your backend's public URL
- Deploy the `frontend/` directory

**Docker:**
```bash
make build-frontend
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=https://your-api.com/api/v1 dingdong-rag-frontend
```

### Infrastructure Checklist

- [ ] PostgreSQL 17 with pgvector extension
- [ ] Neo4j 5 (Community Edition) with APOC plugin
- [ ] Redis 7
- [ ] Supabase project (for file storage) or alternative storage
- [ ] At least one LLM API key (Anthropic or OpenAI)
- [ ] `JWT_SECRET_KEY` set to a strong random value
- [ ] Database migrations applied (`make migrate`)
- [ ] Admin account created (`make seed` or register via API)
- [ ] Google Drive configured (if using base KG ingestion)

## License

Private
