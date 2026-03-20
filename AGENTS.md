# AGENTS.md — DingDong RAG

Orientation guide for AI agents working in this repository.
Read this before touching any code.

---

## What this project is

An agentic Knowledge Graph RAG application. Documents are ingested into a **hybrid retrieval system** (Neo4j graph + pgvector embeddings). An autonomous ReAct RAG agent answers user queries by autonomously selecting retrieval tools (graph, vector, hybrid) and streaming the response with citations via SSE.

**Primary LLM:** Alibaba DashScope `qwen3-max`
**Fallback LLM:** Anthropic `claude-sonnet-4-20250514`
**Embedding model:** Configurable via `EMBEDDING_MODEL` env var (default: `text-embedding-3-small`; also supports `gemini/text-embedding-004` and `text-embedding-v3`)

---

## Repository layout

```
dingdong-rag/
├── backend/                   # FastAPI app (Python 3.12+, uv)
│   ├── app/
│   │   ├── main.py            # App factory + lifespan
│   │   ├── config.py          # Pydantic Settings (all env vars)
│   │   ├── dependencies.py    # FastAPI DI container
│   │   ├── infra/             # Singletons: DB, Neo4j, Redis, LLM, Storage, Worker
│   │   └── domain/            # DDD domain modules
│   │       ├── auth/          # JWT auth, user management
│   │       ├── documents/     # Upload, chunking, TTL lifecycle
│   │       │   └── processors/  # PDF, DOCX — extensible format registry
│   │       ├── knowledge/     # pgvector + Neo4j, hybrid retrieval, KG builder
│   │       ├── agents/        # RAG agent, tools, conversation persistence
│   │       └── ingestion/     # Google Drive sync — IngestionOrchestrator (ReAct) + IngestionSwarm
│   ├── alembic/               # DB migrations
│   └── pyproject.toml
├── frontend/                  # Next.js 16 App Router (TypeScript, Tailwind CSS 4, shadcn/ui)
│   └── src/
│       ├── app/               # Pages: (auth)/ and (dashboard)/
│       ├── components/        # UI components
│       ├── hooks/             # use-auth, use-chat, use-documents, etc.
│       ├── lib/               # api-client.ts (single API entry point)
│       └── types/             # Typed API contracts
├── contracts/
│   └── openapi.yaml           # Source-of-truth API contract
├── .env.example               # All env vars with defaults
├── docker-compose.yml         # Two profiles: `local` and `supabase`
├── Makefile                   # All dev commands (run `make help`)
└── PATTERNS.md                # Golden-path rules — read before adding anything
```

---

## Architecture: how the pieces connect

### Backend process model (two-process monolith)

Two processes share the same codebase but serve different roles:

| Process | How to start | Role |
|---------|-------------|------|
| API server | `uvicorn app.main:app` | Handles HTTP/SSE requests |
| Background worker | `make dev-worker` (or Celery in Docker) | Processes async jobs (documents, ingestion) |

Both connect to the same Postgres, Neo4j, and Redis. Neither imports the other — they communicate only through Celery's Redis broker.

The worker runs:
```
uv run celery -A app.celery_app worker --queues=documents,ingestion --concurrency=4 --pool=threads
```
Four threads poll both queues simultaneously — no starvation between document and ingestion jobs.

### Request lifecycle (chat)

```
Browser  →  POST /api/v1/chat/stream
         →  RAGAgent.chat()
              ├─ Phase 1: LLM decides tool calls (JSON array in response)
              │     └─ Executes: hybrid_search / graph_search / vector_search
              └─ Phase 2: LLM streams answer with citations
         →  SSE events: conversation_created | tool_call | token | citation | done | error
```

### Document ingestion lifecycle

```
User upload                          Google Drive (admin)
     │                                      │
POST /documents/upload            POST /admin/ingestion/trigger
     │                                      │
DocumentService.upload()          IngestionService.trigger_ingestion()
     │                                      │
 process_document_task.delay()      run_ingestion_task.delay()
     │                                      │
     └──────── Celery Worker (Redis broker) ┘
                     │
          ┌──────────┴──────────┐
    DocumentService          IngestionOrchestrator (ReAct agent)
    .process_document()      (via IngestionOrchestrator.run())
          │
     extract text → chunk → embed (pgvector) → KG extraction (Neo4j)
```

### Dual-write: Neo4j + PostgreSQL

Entity and relationship data is **written to both**:
- **Neo4j** — the authoritative graph store (used for Cypher traversals)
- **PostgreSQL** — shadow mirror tables (`knowledge_entities`, `knowledge_relationships`) for SQL joins and counting

When modifying graph operations, always update both stores together via `GraphService`.

---

## Non-obvious gotchas

### 1. Non-standard Docker ports

This project deliberately offsets ports to avoid collisions with other local services:

| Service | Host port | Container port |
|---------|-----------|---------------|
| Neo4j Browser | **17474** | 7474 |
| Neo4j Bolt | **17687** | 7687 |
| Redis | **16379** | 6379 |
| Postgres | 5432 | 5432 |

The `.env.example` reflects the Redis offset (`redis://localhost:16379/0`) but **not** the Neo4j URI offset — it contains `NEO4J_URI=bolt://localhost:7687` (standard port). The actual code default in `config.py:47` is `bolt://localhost:17687`. If you copy `.env.example` to `.env` without changing the Neo4j URI, it will target port 7687, which will fail against a Docker stack where the host-exposed port is 17687. Always override `NEO4J_URI` to `bolt://localhost:17687` when running with Docker.

### 2. Neo4j database name has no underscores

The default database is `dingdongrag` (not `dingdong_rag`). Neo4j database names do not allow underscores. The Docker Compose `NEO4J_initial_dbms_default__database` env var sets this on first boot. If the database is created with the wrong name, you must wipe the Neo4j volume and restart.

### 3. Worker migrated to Celery — `app.infra.worker` is now a shim

The old custom Redis poll loop (`python -m app.infra.worker`) has been replaced by Celery. `app/infra/worker.py` still exists as a **backward-compatibility shim** that re-exports `QUEUE_DOCUMENTS` and `QUEUE_INGESTION` constants (now mapping to Celery queue names) and a no-op `register_handler()`. Any code still importing from `worker` will get the shim without errors, but actual task dispatch is done via Celery `.delay()` in `documents/tasks.py` and `ingestion/tasks.py`.

**To add a new background job:** create a `@celery_app.task` in your domain's `tasks.py`, import it in the router/service, and call `.delay()` — do not use `redis_client.enqueue()`.

### 4. pgvector embeddings use `ARRAY(Float)`, not the `vector` type

Embeddings are stored as `ARRAY(Float)` in SQLAlchemy models (`knowledge/models.py:43`), not as pgvector's native `vector` type. The similarity search queries cast to `::vector` inline in raw SQL (`vector_service.py:137`). If you add vector indexes, you must use a raw Cypher/DDL migration — SQLAlchemy's `ARRAY(Float)` column won't know about the index.

### 5. Supabase pgbouncer disables prepared statements

The database engine is created with `statement_cache_size=0` and `prepared_statement_cache_size=0` (`database.py:42`). This is required because Supabase uses pgbouncer in transaction mode, which does not support prepared statements. **Do not remove these connect_args** — removing them causes cryptic `asyncpg` errors when using Supabase.

### 6. LLM primary is DashScope (Qwen), not Anthropic

Despite the README mentioning Claude prominently, the actual primary model in `.env.example` and `config.py` is:

```
DEFAULT_MODEL=dashscope/qwen3-max
FALLBACK_MODEL=anthropic/claude-sonnet-4-20250514
```

LiteLLM reads `DASHSCOPE_API_KEY` from the environment and routes `dashscope/` prefixed model names to the DashScope international endpoint (`dashscope-intl.aliyuncs.com`). A third provider, **Google Gemini**, is also supported for both LLM calls and embeddings — set `GEMINI_API_KEY` to use `gemini/` prefixed models. **At least one of `DASHSCOPE_API_KEY` or `ANTHROPIC_API_KEY` must be set** — both being empty will cause every LLM call to fail silently with a fallback chain that also fails.

### 7. Two ingestion engines coexist

There are **two separate ingestion classes** that are not interchangeable:

| Class | File | Description |
|-------|------|-------------|
| `IngestionSwarm` | `ingestion/swarm.py` | Pipeline style — scans flat file lists, processes in parallel with semaphore |
| `IngestionOrchestrator` | `ingestion/orchestrator.py` | ReAct agent — LLM drives recursive folder traversal, classifies metadata, uses `batch_ingest_files` tool |

The `IngestionOrchestrator` is the production path (`ingestion/jobs.py` calls it). `IngestionSwarm` is the legacy/simpler path. Both exist in the codebase. Do not assume `IngestionSwarm` is the active engine.

### 8. Google Drive connector calls are now wrapped in `asyncio.to_thread()`

`GoogleDriveConnector` methods (`authenticate()`, `list_files()`, `list_folder_children()`, `download_file()`) are declared `async` and all underlying `google-api-python-client` calls (`.execute()`, `.next_chunk()`) are now wrapped in `asyncio.to_thread()`. This prevents blocking the asyncio event loop during Drive I/O. If you add new Drive API calls, always wrap `.execute()` in `asyncio.to_thread()`.

### 9. Ingestion job "cancel" is cooperative + stale jobs are auto-failed

`IngestionService.cancel_job()` sets the DB status to `CANCELLED` using a direct SQL UPDATE. The `IngestionOrchestrator` polls for cancellation at the start of every agent loop iteration (`_is_cancelled()`) and stops voluntarily when it detects the status change. All status-writing code paths (`_update_job_status()`, `UpdateProgressTool`, `_record_file_event`) use an **atomic WHERE guard** (`status != CANCELLED`) so they never overwrite `CANCELLED`. The cancel is still cooperative (not an immediate kill) -- the orchestrator will finish the current iteration before checking.

**Stale job detection:** `trigger_ingestion()` auto-fails any job that has been in an active state (PENDING/SCANNING/PROCESSING) for longer than 2h15m (the Celery `time_limit` + buffer). This prevents zombie jobs from blocking new triggers forever -- even if the worker crashes, gets SIGKILL'd, or both the orchestrator and task-level error handlers fail.

**Task-level safety net:** The Celery task (`tasks.py`) catches all exceptions from the orchestrator and uses a **fresh DB session** to mark the job as FAILED if the orchestrator's own error handler fails (e.g. because the original session was broken).

### 10. Auto-seed on startup (silent)

At startup, `main.py` calls `_auto_seed_graph_if_empty()`. If Neo4j has zero nodes AND `backend/graph_seed/manifest.json` exists, it runs a full graph import automatically. This is intentional but can be surprising in a fresh environment if you have seed files present — the app will perform a potentially long import before serving its first request.

### 11. ORM dirty-tracking drift with pgbouncer long sessions

The `IngestionOrchestrator` uses direct `SQLAlchemy update()` statements instead of ORM attribute mutation for job status updates (`orchestrator.py:129-147`). This is because pgbouncer transaction mode + long-running async sessions can cause ORM dirty-tracking to lose track of pending changes. **If you add similar long-running services that write to the DB over multiple await points, follow the same pattern** — use `sa_update(...).where(...).values(...)` instead of `obj.field = value; await db.commit()`.

### 12. Token storage is `localStorage`, not cookies

JWT access and refresh tokens are stored in `localStorage` (`api-client.ts:187`, `use-auth.tsx:66`). This means they are accessible to JavaScript (no `httpOnly` protection). This is a known trade-off for simplicity. Do not add `httpOnly` cookie handling without coordinating changes to both `api-client.ts` (SSE streaming logic also reads the token) and the backend CORS/cookie settings.

### 13. `metadata_` Python attribute maps to `metadata` SQL column

SQLAlchemy models in `documents/models.py` and `ingestion/models.py` use `metadata_` as the Python attribute name but `"metadata"` as the actual database column name:

```python
metadata_: Mapped[dict] = mapped_column("metadata", JSONB, ...)
```

This avoids a conflict with SQLAlchemy's reserved `metadata` attribute on the `Base` class. When writing raw SQL or Alembic migrations, use the column name `metadata`, not `metadata_`.

### 14. Document chunks `token_count` is a rough word-count estimate

`DocumentService.process_document()` (`documents/service.py:164`), `IngestionSwarm` (`ingestion/swarm.py:257`), and `IngestionOrchestrator`'s batch tool (`ingestion/orchestrator_tools.py:475`) all compute `token_count` as `len(chunk_data.content.split())` (word count), not actual BPE token count. `VectorService._estimate_tokens()` uses `len(text) // 4`. These are estimates only — do not use them for precise LLM context budgeting.

### 15. `make dev-backend` uses bare `uvicorn`, not `uv run`

The `Makefile` `dev-backend` target runs:
```
cd backend && uvicorn app.main:app ...
```
But without `uv run`. If your shell's `uvicorn` is not inside the `.venv`, this will fail. Use `uv run uvicorn app.main:app --reload` or activate the venv first. The `README.md` "Without Docker" section also has this inconsistency.

### 16. Graph seed schema path is relative to `backend/`

`graph_schema.py:23` resolves the schema dir as:
```python
SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "graph_seed" / "schema"
```
This resolves to `backend/graph_seed/schema/`. The `graph_seed/` directory sits inside `backend/`, not at the repo root. Do not confuse it with a top-level `graph_seed/` that doesn't exist.

### 17. SSE event type resets after every block

The frontend SSE parser in `api-client.ts:139` resets `currentEvent` to `"message"` after dispatching each `data:` line. This is correct per the SSE spec, but it means **every SSE block must include an `event:` line before its `data:` line**. The backend (`agents/router.py:100`) always emits `event: {event.event}\ndata: {event.data}\n\n`. Do not omit the `event:` line in new SSE emitters.

### 18. Celery concurrency eliminates queue starvation

The old sequential Redis poll loop that could starve ingestion jobs behind document jobs has been replaced by Celery with `--concurrency=4 --pool=threads`. All 4 threads poll both `documents` and `ingestion` queues simultaneously. Queue starvation is no longer an issue. To increase throughput, raise `--concurrency` (CPU-bound: use `--pool=prefork`; I/O-bound: keep `--pool=threads`).

### 19. `ingestion/jobs.py` uses `IngestionOrchestrator`, not `IngestionSwarm`

The active job handler registered with the worker is:
```python
# ingestion/jobs.py
orchestrator = IngestionOrchestrator(db=db, storage=storage, connector=connector, llm=llm_provider)
await orchestrator.run(job, admin_user_id, force=force)
```
`IngestionSwarm` is only used if explicitly instantiated by other code. Any modifications to ingestion behavior must target `IngestionOrchestrator`.

---

## Domain modules at a glance

| Domain | Router prefix | Key files | Notes |
|--------|--------------|-----------|-------|
| `auth` | `/auth` | `service.py`, `token.py`, `password.py` | JWT HS256, access 30 min, refresh 7 days |
| `documents` | `/documents` | `service.py`, `processors/`, `jobs.py` | Upload → Redis → worker → process |
| `knowledge` | `/knowledge` | `graph_service.py`, `vector_service.py`, `hybrid_retriever.py`, `kg_builder.py` | Dual-write Neo4j + PG |
| `agents` | `/chat` | `rag_agent.py`, `chat_service.py`, `tools/` | SSE streaming, autonomous tool selection |
| `ingestion` | `/admin/ingestion` | `orchestrator.py`, `drive_connector.py`, `service.py` | Admin-only, ReAct agent loop |

---

## Infrastructure singletons

All infra singletons live in `app/infra/` and are initialized in `main.py` lifespan. They are intentionally module-level globals — not re-created per request.

| Singleton | Module | Init call |
|-----------|--------|-----------|
| `neo4j_client` | `infra/neo4j_client.py` | `await neo4j_client.connect()` |
| `redis_client` | `infra/redis_client.py` | `await redis_client.connect()` |
| `storage_client` | `infra/storage.py` | `storage_client.connect()` (sync) |
| `llm_provider` | `infra/llm.py` | `llm_provider.initialize()` (sync) |
| DB engine | `infra/database.py` | `init_db()` (sync, returns engine + factory) |

The Celery worker process re-initializes all of these independently on startup via `celery_app.py` signals — it does not share the API server's singleton instances across process boundaries.

---

## Adding new code — golden paths

See `PATTERNS.md` for complete golden-path rules. Summary:

- **New endpoint** → add schema → interface → service → router → test → update `contracts/openapi.yaml`
- **New domain** → create full directory with `__init__.py`, `README.md`, `interfaces.py`, `service.py`, `models.py`, `schemas.py`, `router.py`, `exceptions.py`, `tests/`; register router in `main.py`
- **New document format** → create `processors/{format}.py`, implement `AbstractDocumentProcessor`, register in `processors/__init__.py`
- **New agent tool** → create `agents/tools/{tool_name}.py`, implement `IAgentTool`, register in `rag_agent.py` tool list
- **New background job** → create a `@celery_app.task` in your domain's `tasks.py` (see `documents/tasks.py` as a template), import in the router/service, call `.delay()` to dispatch
- **New frontend page** → `app/(dashboard)/{page}/page.tsx`, page-level components in `components/{page}/`, API calls in `hooks/`

**Anti-patterns to avoid:**
- Never put business logic in routers
- Never put API calls directly in page components
- Never modify shadcn/ui components in `components/ui/` — wrap them
- Never run long-running operations synchronously in API handlers
- Never edit applied migrations

---

## Running the project

```bash
# Full local stack
make dev

# Seed dev accounts: admin@dingdong.dev / admin123, user@dingdong.dev / user123
make seed

# Apply Neo4j schema and run migrations
make migrate-local
make graph-schema
```

Services when running:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/v1
- Swagger UI: http://localhost:8000/api/v1/docs
- Health (detailed): http://localhost:8000/api/v1/health/detailed
- Neo4j Browser: http://localhost:17474

---

## Tests

```bash
make test-backend    # pytest with coverage (backend/)
make test-frontend   # vitest (frontend/)
```

Backend tests are co-located inside each domain: `domain/{name}/tests/`. All external services (Neo4j, Supabase, LLM) must be mocked — no tests hit real infrastructure.

---

## Key env vars agents must know about

| Variable | Required | Purpose |
|----------|:--------:|---------|
| `JWT_SECRET_KEY` | Yes | Token signing — change from default in any real environment |
| `DASHSCOPE_API_KEY` | Yes* | Primary LLM (Qwen) |
| `ANTHROPIC_API_KEY` | Yes* | Fallback LLM (Claude) |
| `OPENAI_API_KEY` | No | Used for OpenAI-hosted embedding models (e.g. `text-embedding-3-small`) |
| `GEMINI_API_KEY` | No | Required when using `gemini/` prefixed LLM or embedding models |
| `OPENROUTER_API_KEY` | No | OpenRouter — access 200+ models via a single key (uses `openrouter/` prefix) |
| `EMBEDDING_MODEL` | No | Embedding model name (default: `text-embedding-3-small`) |
| `DATABASE_URL` | No | Defaults to local Docker Postgres |
| `NEO4J_URI` | No | Defaults to `bolt://localhost:17687` |
| `REDIS_URL` | No | Defaults to `redis://localhost:16379/0` |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | No | Only for Supabase file storage |
| `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_SERVICE_ACCOUNT_JSON` | No* | Required for Google Drive ingestion |
| `NEO4J_DATABASE` | No | Defaults to `dingdongrag` (no underscores) |

*At least one LLM key (`DASHSCOPE_API_KEY` or `ANTHROPIC_API_KEY`) must be set.
