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

    async def batch_create_entities(
        self,
        entities: list[EntityCreate],
    ) -> tuple[int, dict[str, uuid.UUID]]:
        """Bulk-create entities. Returns (count, name_lower -> entity_id map)."""
        # Default: sequential fallback
        entity_map: dict[str, uuid.UUID] = {}
        for entity in entities:
            try:
                resp = await self.create_entity(entity)
                entity_map[entity.name.lower()] = resp.id
            except Exception:
                pass
        return len(entity_map), entity_map

    async def batch_create_relationships(
        self,
        raw_relationships: list[dict[str, str]],
        entity_map: dict[str, uuid.UUID],
        document_id: uuid.UUID,
    ) -> int:
        """Bulk-create relationships. Returns count created."""
        count = 0
        for rel in raw_relationships:
            source_id = entity_map.get(rel.get("source", "").lower())
            target_id = entity_map.get(rel.get("target", "").lower())
            if source_id and target_id and source_id != target_id:
                try:
                    await self.create_relationship(RelationshipCreate(
                        source_entity_id=source_id,
                        target_entity_id=target_id,
                        relationship_type=rel.get("type", "RELATED_TO"),
                        properties={"description": rel["description"]} if rel.get("description") else None,
                        source_document_id=document_id,
                    ))
                    count += 1
                except Exception:
                    pass
        return count


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
