# Knowledge Domain

Handles Knowledge Graph construction, vector embeddings, and hybrid retrieval.

## Responsibilities
- Entity and relationship extraction from document chunks
- Neo4j Knowledge Graph CRUD operations
- Vector embedding generation and storage (pgvector)
- Hybrid retrieval (graph + vector, strategy-selectable)
- Graph statistics and exploration

## Key Files
- `interfaces.py` — `KGBuilder`, `VectorStore`, `HybridRetriever` ABCs
- `graph_service.py` — Neo4j graph operations
- `vector_service.py` — pgvector embedding operations
- `hybrid_retriever.py` — Combines graph + vector retrieval
- `models.py` — SQLAlchemy models for embeddings metadata
- `schemas.py` — Pydantic request/response schemas
- `router.py` — Query, stats, exploration endpoints
- `exceptions.py` — Typed knowledge errors

## Adding a New Retrieval Strategy
1. Define strategy interface in `interfaces.py`
2. Implement in `hybrid_retriever.py`
3. Register in the agent's tool selection
4. Write tests in `tests/`
