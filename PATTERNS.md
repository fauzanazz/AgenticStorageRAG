# Golden Paths -- OpenRAG

This document describes the ONE correct way to add each type of component.
AI agents and human developers should follow these paths exactly.

---

## Adding a New API Endpoint

1. Identify which domain it belongs to (auth, documents, knowledge, agents, ingestion)
2. Add the Pydantic request/response schema in `domain/{name}/schemas.py`
3. If new business logic is needed, define the method in `domain/{name}/interfaces.py`
4. Implement the method in `domain/{name}/service.py`
5. Add the endpoint in `domain/{name}/router.py`
6. Write a test in `domain/{name}/tests/test_router.py`
7. Update `contracts/openapi.yaml` to match

**Anti-pattern:** Never define endpoints outside their domain router.

---

## Adding a New Domain

1. Create `backend/app/domain/{name}/` with these files:
   - `__init__.py`
   - `README.md` (AI breadcrumb: purpose, key files, how to add components)
   - `interfaces.py` (ABC contracts)
   - `service.py` (implementation)
   - `models.py` (SQLAlchemy models)
   - `schemas.py` (Pydantic schemas)
   - `router.py` (FastAPI router)
   - `exceptions.py` (typed domain errors)
   - `tests/` directory with test files
2. Register the router in `app/main.py`
3. Add any new dependencies to `app/dependencies.py`

**Anti-pattern:** Never put business logic in routers. Routers call services.

---

## Adding a New Document Processor

1. Create `backend/app/domain/documents/processors/{format}.py`
2. Implement `{Format}Processor(AbstractDocumentProcessor)`
3. Must implement: `extract_text()`, `extract_metadata()`, `extract_chunks()`
4. Register in `processors/__init__.py` format registry
5. Write test in `domain/documents/tests/test_{format}_processor.py`

**Anti-pattern:** Never modify DocumentService to handle a new format. The registry handles dispatch.

---

## Adding a New Agent Tool

1. Create `backend/app/domain/agents/tools/{tool_name}.py`
2. Implement `{ToolName}Tool(AgentTool)`
3. Must implement: `name`, `description`, `execute()` method
4. Register in `rag_agent.py` tool list
5. Write test in `domain/agents/tests/test_{tool_name}_tool.py`

**Anti-pattern:** Never hardcode tool logic inside the agent. Tools are always separate classes.

---

## Adding a New Database Migration

1. Modify or create the SQLAlchemy model in the relevant domain's `models.py`
2. Run `make migration msg="description of change"`
3. Review the generated migration in `backend/alembic/versions/`
4. Run `make migrate` to apply

**Anti-pattern:** Never edit migrations after they've been applied to staging/production.

---

## Adding a New Background Job

1. Define the job function in the relevant domain's `service.py`
2. Register it as a queue handler in `app/infra/worker.py`
3. Dispatch from the service using the queue abstraction
4. Write test that verifies the job runs correctly

**Anti-pattern:** Never run long-running operations synchronously in API handlers. Always queue them.

---

## Adding a New Frontend Page

1. Create `frontend/src/app/(dashboard)/{page-name}/page.tsx`
2. Use the dashboard layout (sidebar + header inherited from layout.tsx)
3. Create page-specific components in `frontend/src/components/{page-name}/`
4. Add API calls using hooks in `frontend/src/hooks/`
5. Add TypeScript types in `frontend/src/types/`

**Anti-pattern:** Never put API calls directly in page components. Always use hooks.

---

## Adding a New UI Component

1. If it's a base/primitive component, add via shadcn CLI: `npx shadcn@latest add {component}`
2. If it's a domain component, create in `frontend/src/components/{domain}/`
3. Co-locate component tests as `{Component}.test.tsx`

**Anti-pattern:** Never modify shadcn/ui components in `components/ui/`. Override with wrapper components.

---

## Writing Tests

### Backend (Python)
- Tests live in `domain/{name}/tests/` (co-located with source)
- File naming: `test_{what_you_test}.py`
- Class naming: `Test{WhatYouTest}`
- Use pytest fixtures for setup
- Use `TestClient` for endpoint tests
- Use mocks for external services (Neo4j, Supabase, LLM)

### Frontend (TypeScript)
- Tests live next to source or in `__tests__/`
- File naming: `{Component}.test.tsx`
- Use React Testing Library for component tests
- Use Vitest for unit tests
- Mock API calls, never hit real backend in unit tests

---

## Naming Conventions

### Python (Backend)
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: prefix with `_`

### TypeScript (Frontend)
- Components: `PascalCase.tsx`
- Hooks: `use{Name}.ts`
- Utilities: `camelCase.ts`
- Types: `PascalCase` in `{domain}.ts`

### Commits
- Follow conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `ci:`
- Scope with domain when relevant: `feat(documents): add DOCX processor`
