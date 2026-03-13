"""Hybrid retriever combining vector and graph search.

Merges results from pgvector similarity search and Neo4j graph
traversal, producing a unified ranked result set.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.knowledge.interfaces import (
    IGraphService,
    IHybridRetriever,
    IVectorService,
)
from app.domain.knowledge.schemas import (
    GraphSearchRequest,
    HybridSearchRequest,
    HybridSearchResult,
    VectorSearchRequest,
)

logger = logging.getLogger(__name__)


class HybridRetriever(IHybridRetriever):
    """Hybrid retrieval combining vector similarity and graph traversal.

    Strategy:
    1. Run vector search and graph search in parallel
    2. Score each result based on configurable weights
    3. Deduplicate results that appear in both
    4. Return merged, sorted results
    """

    def __init__(
        self,
        vector_service: IVectorService,
        graph_service: IGraphService,
    ) -> None:
        self._vector = vector_service
        self._graph = graph_service

    async def search(
        self, request: HybridSearchRequest
    ) -> list[HybridSearchResult]:
        """Execute hybrid search combining vector and graph results."""
        vector_weight = request.vector_weight
        graph_weight = 1.0 - vector_weight

        results: dict[str, HybridSearchResult] = {}

        # Vector search
        if vector_weight > 0:
            try:
                vector_results = await self._vector.search(
                    VectorSearchRequest(
                        query=request.query,
                        top_k=request.top_k,
                        document_id=request.document_id,
                        similarity_threshold=0.5,
                    )
                )

                for vr in vector_results:
                    key = f"chunk:{vr.chunk_id}"
                    results[key] = HybridSearchResult(
                        content=vr.content,
                        source="vector",
                        score=vr.similarity * vector_weight,
                        document_id=vr.document_id,
                        chunk_id=vr.chunk_id,
                        metadata=vr.metadata,
                    )

            except Exception as e:
                logger.warning("Vector search failed in hybrid: %s", e)

        # Graph search
        if graph_weight > 0:
            try:
                graph_results = await self._graph.search_entities(
                    GraphSearchRequest(
                        query=request.query,
                        top_k=request.top_k,
                    )
                )

                for gr in graph_results:
                    key = f"entity:{gr.entity.id}"

                    # Build context from entity and relationships
                    context_parts = [
                        f"Entity: {gr.entity.name} ({gr.entity.entity_type})"
                    ]
                    if gr.entity.description:
                        context_parts.append(gr.entity.description)
                    for rel in gr.relationships[:5]:
                        context_parts.append(
                            f"  - {rel.relationship_type} -> {rel.target_entity_name}"
                        )

                    content = "\n".join(context_parts)

                    if key in results:
                        # Result exists from vector search -- merge
                        existing = results[key]
                        results[key] = HybridSearchResult(
                            content=existing.content,
                            source="both",
                            score=existing.score + gr.relevance_score * graph_weight,
                            document_id=existing.document_id,
                            chunk_id=existing.chunk_id,
                            entity_id=gr.entity.id,
                            metadata=existing.metadata,
                        )
                    else:
                        results[key] = HybridSearchResult(
                            content=content,
                            source="graph",
                            score=gr.relevance_score * graph_weight,
                            entity_id=gr.entity.id,
                            metadata={
                                "entity_type": gr.entity.entity_type,
                                "relationship_count": len(gr.relationships),
                            },
                        )

            except Exception as e:
                logger.warning("Graph search failed in hybrid: %s", e)

        # Sort by score descending
        sorted_results = sorted(
            results.values(),
            key=lambda r: r.score,
            reverse=True,
        )

        return sorted_results[: request.top_k]
