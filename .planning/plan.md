# DingDong RAG -- Implementation Plan

**Approach:** Modular Monolith (Domain-Driven) with AI-Friendly Architecture
**Spec:** `.planning/spec.md` (confirmed 2026-03-13)

---

## Project Structure

```
dingdong-rag/
├── .planning/                     # Specs, plans, ADRs, handoffs
│   ├── spec.md
│   ├── plan.md
│   └── adr/
├── .github/
│   └── workflows/
│       ├── ci-backend.yml         # Python lint + test + type-check
│       ├── ci-frontend.yml        # TS lint + test + type-check + build
│       ├── security.yml           # Trivy scan
│       └── deploy.yml             # Build + push ECR + deploy
├── backend/
│   ├── pyproject.toml             # Single source of truth for deps
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI app factory
│   │   ├── config.py              # Pydantic Settings (env-based)
│   │   ├── dependencies.py        # DI container / provider
│   │   │
│   │   ├── domain/                # Business domains (strict boundaries)
│   │   │   ├── auth/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── README.md      # AI breadcrumb
│   │   │   │   ├── interfaces.py  # ABC contracts
│   │   │   │   ├── service.py     # AuthService implementation
│   │   │   │   ├── models.py      # SQLAlchemy models
│   │   │   │   ├── schemas.py     # Pydantic request/response
│   │   │   │   ├── router.py      # FastAPI router
│   │   │   │   ├── exceptions.py  # Typed domain errors
│   │   │   │   └── tests/
│   │   │   │       ├── test_service.py
│   │   │   │       └── test_router.py
│   │   │   │
│   │   │   ├── documents/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── README.md
│   │   │   │   ├── interfaces.py  # DocumentProcessor ABC
│   │   │   │   ├── service.py     # DocumentService
│   │   │   │   ├── processors/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── base.py    # AbstractDocumentProcessor
│   │   │   │   │   ├── pdf.py     # PdfProcessor(AbstractDocumentProcessor)
│   │   │   │   │   └── docx.py    # DocxProcessor(AbstractDocumentProcessor)
│   │   │   │   ├── models.py
│   │   │   │   ├── schemas.py
│   │   │   │   ├── router.py
│   │   │   │   ├── exceptions.py
│   │   │   │   └── tests/
│   │   │   │       ├── test_service.py
│   │   │   │       ├── test_pdf_processor.py
│   │   │   │       └── test_docx_processor.py
│   │   │   │
│   │   │   ├── knowledge/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── README.md
│   │   │   │   ├── interfaces.py  # KGBuilder ABC, VectorStore ABC
│   │   │   │   ├── graph_service.py    # Neo4j KG operations
│   │   │   │   ├── vector_service.py   # pgvector operations
│   │   │   │   ├── hybrid_retriever.py # Combines graph + vector
│   │   │   │   ├── models.py
│   │   │   │   ├── schemas.py
│   │   │   │   ├── router.py
│   │   │   │   ├── exceptions.py
│   │   │   │   └── tests/
│   │   │   │
│   │   │   ├── agents/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── README.md
│   │   │   │   ├── interfaces.py       # Agent ABC, Tool ABC
│   │   │   │   ├── rag_agent.py        # Main RAG agent (LangChain)
│   │   │   │   ├── extraction_agent.py # KG extraction from docs
│   │   │   │   ├── tools/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── graph_search.py
│   │   │   │   │   ├── vector_search.py
│   │   │   │   │   ├── clarify.py
│   │   │   │   │   └── evaluate.py
│   │   │   │   ├── schemas.py
│   │   │   │   ├── router.py           # Chat / query endpoints
│   │   │   │   ├── exceptions.py
│   │   │   │   └── tests/
│   │   │   │
│   │   │   └── ingestion/
│   │   │       ├── __init__.py
│   │   │       ├── README.md
│   │   │       ├── interfaces.py       # SourceConnector ABC
│   │   │       ├── drive_connector.py  # Google Drive connector
│   │   │       ├── swarm.py            # Agent swarm orchestrator
│   │   │       ├── models.py
│   │   │       ├── schemas.py
│   │   │       ├── router.py           # Trigger ingestion endpoints
│   │   │       ├── exceptions.py
│   │   │       └── tests/
│   │   │
│   │   └── infra/                 # Cross-cutting infrastructure
│   │       ├── __init__.py
│   │       ├── database.py        # Supabase/SQLAlchemy engine
│   │       ├── neo4j_client.py    # Neo4j driver wrapper
│   │       ├── redis_client.py    # Redis connection
│   │       ├── storage.py         # Supabase Storage client
│   │       ├── llm.py             # LiteLLM provider config
│   │       ├── middleware.py      # CORS, auth, logging
│   │       └── worker.py          # Background job runner (Redis queue)
│   │
│   └── scripts/
│       ├── seed.py                # Dev data seeding
│       └── migrate.py             # Migration runner
│
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── Dockerfile
│   ├── src/
│   │   ├── app/                   # Next.js App Router
│   │   │   ├── layout.tsx         # Root layout (mobile-first)
│   │   │   ├── page.tsx           # Landing / redirect
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   └── register/page.tsx
│   │   │   ├── (dashboard)/
│   │   │   │   ├── layout.tsx     # Dashboard shell (sidebar, nav)
│   │   │   │   ├── page.tsx       # Dashboard home
│   │   │   │   ├── documents/
│   │   │   │   │   └── page.tsx   # Upload + manage documents
│   │   │   │   ├── knowledge/
│   │   │   │   │   └── page.tsx   # KG visualization
│   │   │   │   ├── chat/
│   │   │   │   │   └── page.tsx   # RAG chat interface
│   │   │   │   └── settings/
│   │   │   │       └── page.tsx   # User settings, Drive config
│   │   │   └── api/               # BFF API routes (if needed)
│   │   │
│   │   ├── components/            # Shared UI components
│   │   │   ├── ui/                # shadcn/ui components
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── MobileNav.tsx
│   │   │   │   └── Header.tsx
│   │   │   ├── documents/
│   │   │   │   ├── UploadDropzone.tsx
│   │   │   │   └── DocumentList.tsx
│   │   │   ├── knowledge/
│   │   │   │   └── GraphViewer.tsx
│   │   │   └── chat/
│   │   │       ├── ChatWindow.tsx
│   │   │       ├── MessageBubble.tsx
│   │   │       └── CitationCard.tsx
│   │   │
│   │   ├── lib/                   # Utilities and clients
│   │   │   ├── api-client.ts      # Typed fetch wrapper for backend
│   │   │   ├── supabase.ts        # Supabase client (auth)
│   │   │   └── utils.ts
│   │   │
│   │   ├── hooks/                 # Custom React hooks
│   │   │   ├── useChat.ts
│   │   │   ├── useDocuments.ts
│   │   │   └── useKnowledgeGraph.ts
│   │   │
│   │   └── types/                 # Shared TypeScript types
│   │       ├── api.ts             # API response types (mirrors backend schemas)
│   │       ├── documents.ts
│   │       └── chat.ts
│   │
│   └── __tests__/                 # Integration/E2E tests
│
├── contracts/                     # API contracts (source of truth)
│   ├── openapi.yaml               # Backend REST API spec
│   └── events.yaml                # Async event schemas
│
├── docker-compose.yml             # Local dev: Neo4j + Redis + Backend + Frontend
├── docker-compose.prod.yml        # Production overrides
├── .env.example                   # All env vars documented
├── .pre-commit-config.yaml
├── Makefile                       # Developer shortcuts
└── PATTERNS.md                    # Golden paths for AI agents
```

---

## Implementation Waves

Work is organized into waves. Each wave builds on the previous one. Tasks within a wave can run in parallel where indicated.

---

### Wave 0: Project Scaffolding + CI/CD Foundation
**Goal:** Repo structure, tooling, CI green, Docker Compose running -- zero business logic.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 0.1 | Initialize git repo + .gitignore | A | `git init`, Python + Node + Docker gitignore |
| 0.2 | Backend scaffold | A | `pyproject.toml` (ruff, mypy, pytest config), FastAPI app factory, config.py with Pydantic Settings, health endpoint |
| 0.3 | Frontend scaffold | A | `create-next-app` with TS + Tailwind + App Router, shadcn/ui init, health page |
| 0.4 | Docker Compose (local dev) | B (after A) | Neo4j, Redis, Backend, Frontend, Supabase (or local Postgres + pgvector for dev) |
| 0.5 | CI/CD pipelines | A | GitHub Actions: backend lint+test, frontend lint+test+build, Trivy scan |
| 0.6 | Pre-commit hooks | A | ruff, mypy, eslint, prettier, conventional commits |
| 0.7 | `PATTERNS.md` + Golden Paths | A | Document how to add: endpoint, domain, processor, agent tool, test |
| 0.8 | Contracts: OpenAPI skeleton | A | Minimal OpenAPI spec with health endpoint |
| 0.9 | `Makefile` | A | `make dev`, `make test`, `make lint`, `make build`, `make migrate` |

**Exit Criteria:** `make dev` starts all services. `make test` runs and passes. CI is green. No business logic yet.

---

### Wave 1: Infrastructure Layer
**Goal:** All external service connections working. Database, Neo4j, Redis, Storage, LLM -- all wrapped in clean interfaces.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 1.1 | Supabase database setup + SQLAlchemy engine | A | Async engine, session factory, base model class |
| 1.2 | Alembic migrations setup | A | `alembic init`, config wired to app settings |
| 1.3 | Neo4j client wrapper | A | Connection pool, health check, typed query helpers. **Separate database** from existing one |
| 1.4 | Redis client | A | Connection, health check, queue abstraction |
| 1.5 | Supabase Storage client | A | Upload, download, delete, TTL lifecycle policy (7-day) |
| 1.6 | LiteLLM provider setup | A | Claude primary, OpenAI fallback, config-driven model selection |
| 1.7 | Background worker (Redis queue) | B (after 1.4) | Job queue abstraction, worker process, retry logic |
| 1.8 | DI container / dependencies.py | B (after all A) | Wire all infra clients into FastAPI dependency injection |

**Exit Criteria:** Health endpoint reports status of all connections. Worker process starts and processes a dummy job. All infra has unit tests.

---

### Wave 2: Auth Domain
**Goal:** User registration, login, JWT tokens, protected routes.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 2.1 | Auth domain: interfaces + models + schemas | A | User model (multi-tenant ready: org_id field), JWT schema |
| 2.2 | Auth domain: service + router | B (after A) | Register, login, refresh, me endpoints |
| 2.3 | Auth middleware | B (after A) | JWT validation, current_user dependency |
| 2.4 | Frontend: auth pages | A | Login + register pages, auth context/provider, protected routes |
| 2.5 | Frontend: dashboard shell | A | Sidebar, mobile nav, header -- empty pages |

**Exit Criteria:** User can register, login, see dashboard shell. JWT flow works end-to-end. Protected routes redirect unauthenticated users.

---

### Wave 3: Document Domain
**Goal:** Upload files, process them, store temporarily, manage lifecycle.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 3.1 | Document domain: interfaces | A | `AbstractDocumentProcessor` ABC with `extract_text()`, `extract_metadata()`, `extract_chunks()` |
| 3.2 | Document domain: models + schemas | A | Document model (user_id, file_path, status, expires_at, metadata) |
| 3.3 | PDF processor | B (after A) | `PdfProcessor(AbstractDocumentProcessor)` using pypdf or pdfplumber |
| 3.4 | DOCX processor | B (after A) | `DocxProcessor(AbstractDocumentProcessor)` using python-docx |
| 3.5 | Document service | C (after B) | Upload flow: validate -> store in Supabase Storage -> queue processing job -> processor extracts chunks |
| 3.6 | Document router | C (after B) | Upload, list, get, delete endpoints |
| 3.7 | Expiry background job | C (after B) | Cron job: find expired docs, delete from storage + DB + Neo4j + pgvector |
| 3.8 | Frontend: documents page | B | Upload dropzone (drag & drop), document list with status, expiry countdown |

**Exit Criteria:** Upload PDF/DOCX -> processed into chunks -> stored with 7-day expiry. Expired docs cleaned up. Frontend shows upload and list.

---

### Wave 4: Knowledge Domain
**Goal:** Build Knowledge Graph from document chunks. Vector embeddings. Hybrid retrieval.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 4.1 | Knowledge domain: interfaces | A | `KGBuilder` ABC, `VectorStore` ABC, `HybridRetriever` ABC |
| 4.2 | KG extraction agent | B (after A) | LangChain agent that takes document chunks -> extracts entities + relationships -> writes to Neo4j |
| 4.3 | Vector embedding service | B (after A) | Chunk text -> generate embeddings -> store in pgvector |
| 4.4 | Graph service (Neo4j) | B (after A) | CRUD for nodes/relationships, traversal queries, Cypher query builder |
| 4.5 | Hybrid retriever | C (after B) | Combines graph traversal + vector similarity, scoring/ranking, configurable strategy |
| 4.6 | Knowledge router | C (after B) | Query endpoint, graph stats, node/relationship exploration |
| 4.7 | Frontend: KG visualization | B | Interactive graph viewer (d3-force or vis-network), node details panel |

**Exit Criteria:** Upload a document -> KG nodes + relationships created -> embeddings stored -> hybrid query returns relevant results with citations. Graph visualized in UI.

---

### Wave 5: Agent Domain
**Goal:** Full agentic RAG -- autonomous retrieval, multi-hop reasoning, clarifying questions.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 5.1 | Agent domain: interfaces | A | `Agent` ABC, `AgentTool` ABC |
| 5.2 | Agent tools | B (after A) | `GraphSearchTool`, `VectorSearchTool`, `ClarifyTool`, `EvaluateTool` |
| 5.3 | RAG agent (LangChain) | C (after B) | Autonomous agent with tool selection, multi-hop chaining, self-evaluation, streaming responses |
| 5.4 | Chat router (WebSocket) | C (after B) | Streaming chat endpoint, conversation history, citation attachment |
| 5.5 | Frontend: chat interface | B | Chat window, message bubbles, citation cards, streaming display, mobile-optimized |

**Exit Criteria:** User asks a question -> agent autonomously selects tools -> multi-hop if needed -> streams answer with citations. Agent can ask clarifying questions.

---

### Wave 6: Ingestion Domain (Google Drive)
**Goal:** Base KG ingestion from Google Drive via agent swarm. One-time initialization for MVP.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 6.1 | Ingestion domain: interfaces | A | `SourceConnector` ABC |
| 6.2 | Google Drive connector (OAuth2, read-only) | B (after A) | Owner-only OAuth2 consent (one-time browser auth), refresh token stored in env/DB. Read-only scope (`drive.readonly`). List files, download. No write operations. End users cannot connect their own Drive |
| 6.3 | Agent swarm orchestrator | C (after B) | Distributes files across extraction agents, tracks progress, handles failures |
| 6.4 | Ingestion router (admin-only) | C (after B) | Trigger ingestion, check status, view base KG stats. Admin-protected -- not exposed to end users |
| 6.5 | Frontend: admin ingestion panel | B | Admin-only page: trigger ingestion, progress display, base KG stats. Not visible to regular users |

**Exit Criteria:** Connect Google Drive -> trigger ingestion -> swarm processes all files -> base KG populated. Ingestion status visible in UI.

---

### Wave 7: Polish + Hardening
**Goal:** Production-ready quality.

| # | Task | Parallel Group | Details |
|---|------|---------------|---------|
| 7.1 | Error handling audit | A | All domains return typed errors, frontend shows user-friendly messages |
| 7.2 | Loading states + optimistic UI | A | Skeleton loaders, optimistic updates, retry on failure |
| 7.3 | Integration tests | A | End-to-end flows: upload -> process -> query -> answer |
| 7.4 | Security audit | A | OWASP top 10, file upload validation, input sanitization, secrets management |
| 7.5 | Performance optimization | A | Query caching (Redis), lazy loading, bundle optimization |
| 7.6 | Docker production config | B (after A) | Multi-stage builds, health checks, restart policies |
| 7.7 | Deploy pipeline finalization | B (after A) | ECR push, VPS deploy, Vercel deploy, environment management |

**Exit Criteria:** All tests green. Trivy clean. Lighthouse mobile score > 90. Deploy pipeline works end-to-end.

---

## Key Architecture Decisions

### ADR-001: Modular Monolith over Microservices
- **Context:** Solo developer, complex domain, needs clean boundaries but simple deployment
- **Decision:** Single codebase, domain-based modules, two processes (API + worker)
- **Rationale:** Fastest path to production with clean boundaries. Can extract services later

### ADR-002: Contracts First
- **Context:** AI agents will write most implementation code
- **Decision:** OpenAPI spec + Python ABCs + TypeScript types defined before implementation
- **Rationale:** AI produces dramatically better code when coding against a contract

### ADR-003: Separate Neo4j Database
- **Context:** Existing Neo4j instance has data from `research-agentic` project
- **Decision:** Create dedicated `dingdong_rag` database, never share with other projects
- **Rationale:** Data isolation. No risk of contamination

### ADR-004: Hybrid Retrieval (Graph + Vector)
- **Context:** Pure graph or pure vector each miss important results
- **Decision:** Agent autonomously chooses graph traversal, vector similarity, or combination
- **Rationale:** Graph captures relationships/structure, vectors capture semantic similarity. Together they cover more ground

### ADR-005: 7-Day TTL for User Uploads
- **Context:** User doesn't want permanent file storage for uploaded docs
- **Decision:** Supabase Storage lifecycle policy + background cleanup job for graph/vector data
- **Rationale:** Cost control, data hygiene, privacy

### ADR-006: OAuth2 Read-Only for Google Drive (Owner Only)
- **Context:** Base KG ingested from owner's Google Drive. Read-only access. End users never connect their own Drive
- **Decision:** Owner-only OAuth2 with `drive.readonly` scope. One-time browser auth, store refresh token. Admin-only ingestion trigger
- **Rationale:** Simplest secure path. No write risk. No user-facing OAuth complexity. Base KG is a curated, admin-controlled source of truth

---

## AI Architecture Compliance

Per the AI-Friendly Architecture Guide, this plan ensures:

- [x] **Contracts first** -- OpenAPI + ABCs defined before implementation
- [x] **Golden paths** -- `PATTERNS.md` documents how to add each component type
- [x] **Domain-based structure** -- grouped by business domain, not file type
- [x] **Descriptive naming** -- `PdfProcessor`, `GraphSearchTool`, `HybridRetriever`
- [x] **Co-located tests** -- each domain has its own `tests/` directory
- [x] **Explicit imports** -- no barrel files, direct imports
- [x] **ADRs** -- key decisions documented
- [x] **README breadcrumbs** -- each domain has a README.md
- [x] **Typed errors** -- each domain has `exceptions.py`
- [x] **Env config** -- `.env.example` with all vars documented
