"""Tests for hybrid retriever."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.knowledge.hybrid_retriever import HybridRetriever
from app.domain.knowledge.schemas import (
    EntityResponse,
    GraphSearchResult,
    HybridSearchRequest,
    VectorSearchResult,
)


@pytest.fixture
def mock_vector() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_graph() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def retriever(mock_vector: AsyncMock, mock_graph: AsyncMock) -> HybridRetriever:
    return HybridRetriever(vector_service=mock_vector, graph_service=mock_graph)


class TestHybridSearch:
    """Tests for hybrid retrieval."""

    @pytest.mark.asyncio
    async def test_vector_only_search(
        self, retriever: HybridRetriever, mock_vector: AsyncMock, mock_graph: AsyncMock
    ) -> None:
        """With vector_weight=1.0, only vector results should appear."""
        chunk_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        mock_vector.search.return_value = [
            VectorSearchResult(
                chunk_id=chunk_id,
                document_id=doc_id,
                content="Vector result",
                similarity=0.9,
            )
        ]

        results = await retriever.search(
            HybridSearchRequest(query="test", vector_weight=1.0)
        )

        assert len(results) == 1
        assert results[0].source == "vector"
        assert results[0].score == 0.9
        mock_graph.search_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_only_search(
        self, retriever: HybridRetriever, mock_vector: AsyncMock, mock_graph: AsyncMock
    ) -> None:
        """With vector_weight=0.0, only graph results should appear."""
        now = datetime.now(timezone.utc)

        mock_graph.search_entities.return_value = [
            GraphSearchResult(
                entity=EntityResponse(
                    id=uuid.uuid4(),
                    neo4j_id="neo-1",
                    entity_type="Person",
                    name="John",
                    created_at=now,
                    updated_at=now,
                ),
                relevance_score=0.8,
            )
        ]

        results = await retriever.search(
            HybridSearchRequest(query="test", vector_weight=0.0)
        )

        assert len(results) == 1
        assert results[0].source == "graph"
        assert results[0].score == 0.8
        mock_vector.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_search(
        self, retriever: HybridRetriever, mock_vector: AsyncMock, mock_graph: AsyncMock
    ) -> None:
        """With balanced weights, both results should appear sorted by score."""
        now = datetime.now(timezone.utc)
        chunk_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        mock_vector.search.return_value = [
            VectorSearchResult(
                chunk_id=chunk_id,
                document_id=doc_id,
                content="Vector result",
                similarity=0.95,
            )
        ]

        mock_graph.search_entities.return_value = [
            GraphSearchResult(
                entity=EntityResponse(
                    id=uuid.uuid4(),
                    neo4j_id="neo-1",
                    entity_type="Concept",
                    name="Machine Learning",
                    created_at=now,
                    updated_at=now,
                ),
                relevance_score=0.7,
            )
        ]

        results = await retriever.search(
            HybridSearchRequest(query="test", vector_weight=0.5)
        )

        assert len(results) == 2
        # Vector: 0.95 * 0.5 = 0.475, Graph: 0.7 * 0.5 = 0.35
        assert results[0].source == "vector"
        assert results[1].source == "graph"

    @pytest.mark.asyncio
    async def test_vector_failure_degrades_gracefully(
        self, retriever: HybridRetriever, mock_vector: AsyncMock, mock_graph: AsyncMock
    ) -> None:
        """If vector search fails, graph results should still be returned."""
        now = datetime.now(timezone.utc)

        mock_vector.search.side_effect = Exception("Vector DB down")
        mock_graph.search_entities.return_value = [
            GraphSearchResult(
                entity=EntityResponse(
                    id=uuid.uuid4(),
                    neo4j_id="neo-1",
                    entity_type="Person",
                    name="Jane",
                    created_at=now,
                    updated_at=now,
                ),
                relevance_score=0.9,
            )
        ]

        results = await retriever.search(
            HybridSearchRequest(query="test", vector_weight=0.5)
        )

        assert len(results) == 1
        assert results[0].source == "graph"

    @pytest.mark.asyncio
    async def test_respects_top_k(
        self, retriever: HybridRetriever, mock_vector: AsyncMock, mock_graph: AsyncMock
    ) -> None:
        """Results should be limited to top_k."""
        mock_vector.search.return_value = [
            VectorSearchResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                content=f"Result {i}",
                similarity=0.9 - i * 0.1,
            )
            for i in range(5)
        ]
        mock_graph.search_entities.return_value = []

        results = await retriever.search(
            HybridSearchRequest(query="test", top_k=3, vector_weight=1.0)
        )

        assert len(results) == 3
