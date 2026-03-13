"""Knowledge domain API router.

Endpoints for knowledge graph operations, search, and visualization.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.domain.auth.models import User
from app.domain.knowledge.exceptions import (
    EntityNotFoundError,
    GraphQueryError,
    KnowledgeBaseError,
)
from app.domain.knowledge.graph_service import GraphService
from app.domain.knowledge.hybrid_retriever import HybridRetriever
from app.domain.knowledge.schemas import (
    EntityCreate,
    EntityResponse,
    EntityWithRelationships,
    GraphVisualization,
    HybridSearchRequest,
    HybridSearchResult,
    KnowledgeStats,
    RelationshipCreate,
    RelationshipResponse,
    VectorSearchRequest,
    VectorSearchResult,
)
from app.domain.knowledge.vector_service import VectorService
from app.infra.neo4j_client import neo4j_client

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Dependency helpers ──────────────────────────────────────────────────


def _get_graph_service(db: AsyncSession = Depends(get_db)) -> GraphService:
    return GraphService(db=db, neo4j=neo4j_client)


def _get_vector_service(db: AsyncSession = Depends(get_db)) -> VectorService:
    return VectorService(db=db)


def _get_hybrid_retriever(
    db: AsyncSession = Depends(get_db),
) -> HybridRetriever:
    return HybridRetriever(
        vector_service=VectorService(db=db),
        graph_service=GraphService(db=db, neo4j=neo4j_client),
    )


# ── Entity endpoints ───────────────────────────────────────────────────


@router.post("/entities", response_model=EntityResponse, status_code=201)
async def create_entity(
    entity: EntityCreate,
    user: User = Depends(get_current_user),
    graph: GraphService = Depends(_get_graph_service),
) -> EntityResponse:
    """Create a new entity in the knowledge graph."""
    try:
        return await graph.create_entity(entity)
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.get("/entities/{entity_id}", response_model=EntityWithRelationships)
async def get_entity(
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    graph: GraphService = Depends(_get_graph_service),
) -> EntityWithRelationships:
    """Get entity with its relationships."""
    try:
        return await graph.get_entity(entity_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=500, detail=e.message) from e


# ── Relationship endpoints ─────────────────────────────────────────────


@router.post("/relationships", response_model=RelationshipResponse, status_code=201)
async def create_relationship(
    relationship: RelationshipCreate,
    user: User = Depends(get_current_user),
    graph: GraphService = Depends(_get_graph_service),
) -> RelationshipResponse:
    """Create a relationship between two entities."""
    try:
        return await graph.create_relationship(relationship)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


# ── Search endpoints ───────────────────────────────────────────────────


@router.post("/search/vector", response_model=list[VectorSearchResult])
async def vector_search(
    request: VectorSearchRequest,
    user: User = Depends(get_current_user),
    vector: VectorService = Depends(_get_vector_service),
) -> list[VectorSearchResult]:
    """Search by vector similarity."""
    try:
        return await vector.search(request)
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=500, detail=e.message) from e


@router.post("/search/hybrid", response_model=list[HybridSearchResult])
async def hybrid_search(
    request: HybridSearchRequest,
    user: User = Depends(get_current_user),
    retriever: HybridRetriever = Depends(_get_hybrid_retriever),
) -> list[HybridSearchResult]:
    """Hybrid search combining vector and graph results."""
    try:
        return await retriever.search(request)
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=500, detail=e.message) from e


# ── Visualization endpoints ───────────────────────────────────────────


@router.get("/graph", response_model=GraphVisualization)
async def get_graph(
    document_id: uuid.UUID | None = Query(None),
    entity_types: str | None = Query(None, description="Comma-separated entity types"),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    graph: GraphService = Depends(_get_graph_service),
) -> GraphVisualization:
    """Get graph data for visualization."""
    try:
        types_list = entity_types.split(",") if entity_types else None
        return await graph.get_graph_visualization(
            document_id=document_id,
            entity_types=types_list,
            limit=limit,
        )
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=500, detail=e.message) from e


@router.get("/stats", response_model=KnowledgeStats)
async def get_stats(
    user: User = Depends(get_current_user),
    graph: GraphService = Depends(_get_graph_service),
) -> KnowledgeStats:
    """Get knowledge graph statistics."""
    try:
        return await graph.get_stats()
    except KnowledgeBaseError as e:
        raise HTTPException(status_code=500, detail=e.message) from e
