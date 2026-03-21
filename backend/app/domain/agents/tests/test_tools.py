"""Tests for agent tools."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.domain.agents.tools.graph_search import GraphSearchTool
from app.domain.agents.tools.hybrid_search import HybridSearchTool
from app.domain.agents.tools.vector_search import VectorSearchTool
from app.domain.knowledge.schemas import (
    EntityResponse,
    GraphSearchResult,
    HybridSearchResult,
    VectorSearchResult,
)


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


class TestGraphSearchTool:
    """Tests for graph search tool."""

    def test_name(self) -> None:
        tool = GraphSearchTool(graph_service=AsyncMock())
        assert tool.name == "graph_search"

    def test_description_not_empty(self) -> None:
        tool = GraphSearchTool(graph_service=AsyncMock())
        assert len(tool.description) > 20

    @pytest.mark.asyncio
    async def test_execute_success(self, now: datetime) -> None:
        mock_graph = AsyncMock()
        mock_graph.search_entities.return_value = [
            GraphSearchResult(
                entity=EntityResponse(
                    id=uuid.uuid4(),
                    neo4j_id="neo-1",
                    entity_type="Person",
                    name="John",
                    description="Engineer",
                    created_at=now,
                    updated_at=now,
                ),
                relationships=[],
                relevance_score=0.9,
            )
        ]

        tool = GraphSearchTool(graph_service=mock_graph)
        result = await tool.execute(query="John")

        assert result["count"] == 1
        assert result["source"] == "knowledge_graph"
        assert result["result"][0]["entity_name"] == "John"

    @pytest.mark.asyncio
    async def test_execute_empty_query(self) -> None:
        tool = GraphSearchTool(graph_service=AsyncMock())
        result = await tool.execute(query="")

        assert result["result"] == []
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_handles_error(self) -> None:
        mock_graph = AsyncMock()
        mock_graph.search_entities.side_effect = Exception("Neo4j down")

        tool = GraphSearchTool(graph_service=mock_graph)
        result = await tool.execute(query="test")

        assert result["result"] == []
        assert "error" in result


class TestVectorSearchTool:
    """Tests for vector search tool."""

    def test_name(self) -> None:
        tool = VectorSearchTool(vector_service=AsyncMock())
        assert tool.name == "vector_search"

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        mock_vector = AsyncMock()
        mock_vector.search.return_value = [
            VectorSearchResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                content="Test content about AI",
                similarity=0.92,
            )
        ]

        tool = VectorSearchTool(vector_service=mock_vector)
        result = await tool.execute(query="AI")

        assert result["count"] == 1
        assert result["source"] == "vector_search"
        assert result["result"][0]["similarity"] == 0.92

    @pytest.mark.asyncio
    async def test_execute_empty_query(self) -> None:
        tool = VectorSearchTool(vector_service=AsyncMock())
        result = await tool.execute(query="")
        assert result["result"] == []

    @pytest.mark.asyncio
    async def test_execute_handles_error(self) -> None:
        mock_vector = AsyncMock()
        mock_vector.search.side_effect = Exception("pgvector error")

        tool = VectorSearchTool(vector_service=mock_vector)
        result = await tool.execute(query="test")
        assert result["result"] == []


class TestHybridSearchTool:
    """Tests for hybrid search tool."""

    def test_name(self) -> None:
        tool = HybridSearchTool(hybrid_retriever=AsyncMock())
        assert tool.name == "hybrid_search"

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.search.return_value = [
            HybridSearchResult(
                content="Combined result",
                source="both",
                score=0.88,
                document_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
            )
        ]

        tool = HybridSearchTool(hybrid_retriever=mock_retriever)
        result = await tool.execute(query="test", vector_weight=0.6)

        assert result["count"] == 1
        assert result["source"] == "hybrid"
        assert result["result"][0]["source"] == "both"

    @pytest.mark.asyncio
    async def test_execute_empty_query(self) -> None:
        tool = HybridSearchTool(hybrid_retriever=AsyncMock())
        result = await tool.execute(query="")
        assert result["result"] == []
