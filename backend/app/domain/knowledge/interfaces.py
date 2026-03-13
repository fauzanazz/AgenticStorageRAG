"""Knowledge domain interfaces.

Abstract base classes defining the contracts for knowledge services.
Implementations can be swapped without changing consumers.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.domain.knowledge.schemas import (
    EntityCreate,
    EntityResponse,
    EntityWithRelationships,
    GraphSearchRequest,
    GraphSearchResult,
    GraphVisualization,
    HybridSearchRequest,
    HybridSearchResult,
    KnowledgeStats,
    RelationshipCreate,
    RelationshipResponse,
    VectorSearchRequest,
    VectorSearchResult,
)


class IGraphService(ABC):
    """Interface for knowledge graph operations (Neo4j)."""

    @abstractmethod
    async def create_entity(
        self, entity: EntityCreate
    ) -> EntityResponse:
        """Create an entity node in the graph."""
        ...

    @abstractmethod
    async def get_entity(
        self, entity_id: uuid.UUID
    ) -> EntityWithRelationships:
        """Get entity with its relationships."""
        ...

    @abstractmethod
    async def search_entities(
        self, request: GraphSearchRequest
    ) -> list[GraphSearchResult]:
        """Search entities by query, traversing the graph."""
        ...

    @abstractmethod
    async def create_relationship(
        self, relationship: RelationshipCreate
    ) -> RelationshipResponse:
        """Create a relationship between two entities."""
        ...

    @abstractmethod
    async def get_graph_visualization(
        self,
        document_id: uuid.UUID | None = None,
        entity_types: list[str] | None = None,
        limit: int = 100,
    ) -> GraphVisualization:
        """Get graph data formatted for visualization."""
        ...

    @abstractmethod
    async def get_stats(self) -> KnowledgeStats:
        """Get knowledge graph statistics."""
        ...

    @abstractmethod
    async def delete_document_entities(
        self, document_id: uuid.UUID
    ) -> int:
        """Delete all entities and relationships for a document."""
        ...


class IVectorService(ABC):
    """Interface for vector embedding operations (pgvector)."""

    @abstractmethod
    async def embed_chunks(
        self,
        chunks: list[dict[str, Any]],
        document_id: uuid.UUID,
    ) -> int:
        """Generate and store embeddings for document chunks.

        Args:
            chunks: List of dicts with 'id', 'content', 'metadata' keys.
            document_id: The source document ID.

        Returns:
            Number of embeddings created.
        """
        ...

    @abstractmethod
    async def search(
        self, request: VectorSearchRequest
    ) -> list[VectorSearchResult]:
        """Search by vector similarity."""
        ...

    @abstractmethod
    async def delete_document_embeddings(
        self, document_id: uuid.UUID
    ) -> int:
        """Delete all embeddings for a document."""
        ...


class IHybridRetriever(ABC):
    """Interface for hybrid retrieval (vector + graph)."""

    @abstractmethod
    async def search(
        self, request: HybridSearchRequest
    ) -> list[HybridSearchResult]:
        """Execute a hybrid search combining vector and graph results."""
        ...


class IKGBuilder(ABC):
    """Interface for building knowledge graph from documents.

    Implementations use LLM to extract entities and relationships
    from document chunks and populate the graph.
    """

    @abstractmethod
    async def build_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        document_id: uuid.UUID,
    ) -> dict[str, int]:
        """Extract entities and relationships from chunks and add to graph.

        Returns:
            Dict with 'entities_created' and 'relationships_created' counts.
        """
        ...
