# DingDong RAG -- Specification

## 1. One-Line Summary

An agentic Knowledge Graph RAG web application that ingests documents (PDF, DOCX, extensible) into a hybrid retrieval system (Neo4j graph + pgvector), with an autonomous AI agent that reasons over the knowledge to answer user queries through a SaaS-quality, mobile-first web interface.

## 2. Target Users

- **Phase 1:** Single developer/power-user (you) for personal knowledge management and research.
- **Phase 2:** End users -- multi-tenancy support architected from the start so onboarding external users requires no rewrite.

## 3. Success Criteria

A user can:

1. Log in and see a polished SaaS dashboard (mobile-first).
2. Upload PDF or DOCX files through the UI.
3. The system autonomously extracts entities, relationships, and claims into a Knowledge Graph (Neo4j).
4. Visualize the knowledge graph (nodes, edges, clusters) interactively.
5. Open a conversational chat interface and ask questions.
6. The agentic system autonomously decides retrieval strategy -- graph traversal, vector similarity, hybrid combination, or asks a clarifying question.
7. Answers include citations pointing to source documents and locations.
8. User-uploaded documents auto-expire after 7 days (Supabase Storage TTL).
9. Base Knowledge (source of truth) is ingested from Google Drive via an agent swarm and persists indefinitely.

## 4. Two-Tier Knowledge Architecture

### Tier 1: Base Knowledge Graph (Source of Truth)
- **Source:** Google Drive (user provides access credentials/API key).
- **Ingestion:** Agent swarm autonomously processes all files in the configured Drive folder.
- **Persistence:** Permanent. This is the canonical knowledge base.
- **Scope:** All supported file types in the Drive.

### Tier 2: Ephemeral User Uploads
- **Source:** User uploads via web UI.
- **Supported Formats:** PDF, DOCX (initially). Interface-based design allows adding new formats.
- **Storage:** Supabase Storage with 7-day TTL lifecycle policy.
- **Graph Integration:** Extracted knowledge is added to Neo4j with source metadata and expiry tracking.
- **Cleanup:** Background job removes expired graph nodes/vectors when source files expire.

## 5. Agentic Behavior

The system is NOT a simple retrieve-and-answer pipeline. The agent autonomously:

- **Plans** its retrieval strategy per query (graph-first, vector-first, hybrid, multi-hop).
- **Chains** multiple retrievals when a single pass is insufficient (multi-hop reasoning).
- **Decides** when to ask the user a clarifying question instead of guessing.
- **Self-evaluates** its answer quality and retries with different strategies if confidence is low.
- **Orchestrates** sub-agents for document ingestion (agent swarm for Google Drive).

## 6. Explicit Out of Scope

- Real-time multi-user collaboration on graphs
- Native mobile app (mobile-first web only)
- Fine-tuning or training custom models
- Payment / billing system
- Self-hosted LLM inference
- Automated Google Drive sync/watch (manual trigger for base KG ingestion)

## 7. Tech Stack

### Frontend
| Concern         | Technology                          |
|-----------------|-------------------------------------|
| Framework       | Next.js 15 (App Router)             |
| Language        | TypeScript (strict mode)            |
| Styling         | Tailwind CSS                        |
| Components      | shadcn/ui                           |
| Design          | Mobile-first responsive             |
| Deploy          | Vercel                              |

### Backend
| Concern         | Technology                          |
|-----------------|-------------------------------------|
| Framework       | FastAPI                             |
| Language        | Python 3.12+ (OOP, strict typing)   |
| ORM             | SQLAlchemy 2.0 (async)              |
| Database        | Supabase PostgreSQL                 |
| Vector Store    | Supabase pgvector                   |
| Knowledge Graph | Neo4j (separate database instance)  |
| Cache / Queue   | Redis                               |
| File Storage    | Supabase Storage (7-day TTL)        |
| AI Abstraction  | LangChain + LiteLLM                 |
| Primary LLM     | Anthropic Claude                    |
| Fallback LLM    | OpenAI GPT                          |

### Infrastructure
| Concern         | Technology                          |
|-----------------|-------------------------------------|
| Local Dev       | Docker Compose                      |
| Backend Deploy  | VPS                                 |
| Frontend Deploy | Vercel                              |
| CI/CD           | GitHub Actions                      |
| Security Scan   | Trivy                               |
| Container Reg   | AWS ECR                             |

### Quality
| Concern         | Technology                          |
|-----------------|-------------------------------------|
| Python Testing  | pytest + pytest-asyncio + coverage  |
| Frontend Test   | Vitest + React Testing Library      |
| Linting (Py)    | ruff                                |
| Linting (TS)    | ESLint + Prettier                   |
| Type Checking   | mypy (Python) + tsc (TypeScript)    |
| Pre-commit      | pre-commit hooks                    |

## 8. Architecture Principles

- **OOP best practices** -- clean class hierarchies, SOLID principles, dependency injection.
- **Interface-based file processing** -- abstract `DocumentProcessor` interface; PDF and DOCX are concrete implementations. Adding a new format = adding one class.
- **Multi-tenant ready** -- user/org scoping on all database models from day one.
- **API-first** -- FastAPI serves a clean REST/WebSocket API; frontend is a pure consumer.
- **Hybrid retrieval** -- every query can use graph traversal (Neo4j), vector similarity (pgvector), or both, decided autonomously by the agent.
- **Production-grade** -- CI/CD pipeline, unit tests, integration tests, security scanning, typed code throughout.

## 9. Non-Functional Requirements

- **Response time:** Agent should begin streaming a response within 3 seconds of query submission.
- **Upload limit:** Support files up to 50MB per upload.
- **Graph scale:** Handle knowledge graphs up to 100K nodes and 500K relationships without degradation.
- **Availability:** Backend designed for single-instance VPS initially but stateless enough to scale horizontally.
- **Security:** OWASP top 10 covered. File uploads validated and sandboxed. API keys never exposed to frontend.
