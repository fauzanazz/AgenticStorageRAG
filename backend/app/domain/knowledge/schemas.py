"""Knowledge domain schemas.

Pydantic models for API request/response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------


class EntityBase(BaseModel):
    """Shared entity fields."""

    entity_type: str = Field(
        ..., description="Type/label of the entity (e.g., Person, Concept, Organization)"
    )
    name: str = Field(..., max_length=500, description="Entity name")
    description: str | None = Field(None, description="Entity description")
    properties: dict | None = Field(None, description="Additional entity properties")


class EntityCreate(EntityBase):
    """Schema for creating an entity."""

    source_document_id: uuid.UUID | None = None


class EntityResponse(EntityBase):
    """Schema for entity API responses."""

    id: uuid.UUID
    neo4j_id: str
    source_document_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    relationship_count: int = 0

    model_config = {"from_attributes": True}


class EntityWithRelationships(EntityResponse):
    """Entity with its relationships expanded."""

    relationships: list[RelationshipResponse] = []


# ---------------------------------------------------------------------------
# Relationship schemas
# ---------------------------------------------------------------------------


class RelationshipBase(BaseModel):
    """Shared relationship fields."""

    relationship_type: str = Field(
        ..., description="Type of relationship (e.g., WORKS_AT, RELATED_TO)"
    )
    properties: dict | None = Field(None, description="Additional relationship properties")
    weight: float = Field(1.0, ge=0.0, le=1.0, description="Relationship strength/confidence")


class RelationshipCreate(RelationshipBase):
    """Schema for creating a relationship."""

    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    source_document_id: uuid.UUID | None = None


class RelationshipResponse(RelationshipBase):
    """Schema for relationship API responses."""

    id: uuid.UUID
    neo4j_id: str
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    source_entity_name: str | None = None
    target_entity_name: str | None = None
    source_document_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Search / retrieval schemas
# ---------------------------------------------------------------------------


class VectorSearchRequest(BaseModel):
    """Request for vector similarity search."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    document_id: uuid.UUID | None = Field(None, description="Filter by document")
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0)


class VectorSearchResult(BaseModel):
    """A single vector search result."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    similarity: float
    metadata: dict | None = None


class GraphSearchRequest(BaseModel):
    """Request for knowledge graph traversal."""

    query: str = Field(..., min_length=1, max_length=2000)
    entity_types: list[str] | None = Field(None, description="Filter by entity types")
    max_depth: int = Field(2, ge=1, le=5, description="Max traversal depth")
    top_k: int = Field(10, ge=1, le=50)


class GraphSearchResult(BaseModel):
    """A single graph search result."""

    entity: EntityResponse
    relationships: list[RelationshipResponse] = []
    relevance_score: float = 0.0
    path_description: str | None = None


class HybridSearchRequest(BaseModel):
    """Request for hybrid (vector + graph) search."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    vector_weight: float = Field(
        0.5, ge=0.0, le=1.0, description="Weight for vector results (1 - this = graph weight)"
    )
    document_id: uuid.UUID | None = None


class HybridSearchResult(BaseModel):
    """Combined search result from both vector and graph."""

    content: str
    source: str = Field(..., description="'vector', 'graph', or 'both'")
    score: float
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    metadata: dict | None = None


# ---------------------------------------------------------------------------
# Graph visualization schemas
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """Node for graph visualization."""

    id: str
    label: str
    type: str
    description: str | None = None
    properties: dict | None = None
    size: float = 1.0


class GraphEdge(BaseModel):
    """Edge for graph visualization."""

    source: str
    target: str
    label: str
    weight: float = 1.0


class GraphVisualization(BaseModel):
    """Full graph data for visualization."""

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    total_nodes: int = 0
    total_edges: int = 0


# ---------------------------------------------------------------------------
# Knowledge stats
# ---------------------------------------------------------------------------


class KnowledgeStats(BaseModel):
    """Statistics about the knowledge graph."""

    total_entities: int = 0
    total_relationships: int = 0
    total_embeddings: int = 0
    entity_types: dict[str, int] = {}
    relationship_types: dict[str, int] = {}
