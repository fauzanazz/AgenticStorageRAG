"""Tests for KG builder."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.knowledge.kg_builder import KGBuilder, _parse_json_response
from app.domain.knowledge.schemas import EntityResponse


@pytest.fixture
def mock_graph() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def builder(mock_graph: AsyncMock, mock_llm: AsyncMock) -> KGBuilder:
    return KGBuilder(graph_service=mock_graph, llm=mock_llm)


class TestParseJsonResponse:
    """Tests for JSON response parsing."""

    def test_direct_json(self) -> None:
        result = _parse_json_response('{"entities": [], "relationships": []}')
        assert result == {"entities": [], "relationships": []}

    def test_json_in_code_block(self) -> None:
        text = '```json\n{"entities": [{"name": "Test", "type": "Person"}], "relationships": []}\n```'
        result = _parse_json_response(text)
        assert result is not None
        assert len(result["entities"]) == 1

    def test_json_in_plain_code_block(self) -> None:
        text = '```\n{"entities": [], "relationships": []}\n```'
        result = _parse_json_response(text)
        assert result == {"entities": [], "relationships": []}

    def test_json_embedded_in_text(self) -> None:
        text = 'Here is the result: {"entities": [], "relationships": []} end.'
        result = _parse_json_response(text)
        assert result == {"entities": [], "relationships": []}

    def test_invalid_json(self) -> None:
        result = _parse_json_response("This is not JSON at all")
        assert result is None

    def test_empty_string(self) -> None:
        result = _parse_json_response("")
        assert result is None


class TestBuildFromChunks:
    """Tests for KG building from document chunks."""

    @pytest.mark.asyncio
    async def test_empty_chunks(self, builder: KGBuilder) -> None:
        result = await builder.build_from_chunks([], uuid.uuid4())
        assert result == {"entities_created": 0, "relationships_created": 0}

    @pytest.mark.asyncio
    async def test_build_with_entities(
        self, builder: KGBuilder, mock_graph: AsyncMock, mock_llm: AsyncMock
    ) -> None:
        doc_id = uuid.uuid4()
        chunks = [
            {"id": uuid.uuid4(), "content": "John works at Acme Corp.", "metadata": {}},
        ]

        # Mock LLM extraction response
        extraction_json = json.dumps({
            "entities": [
                {"name": "John", "type": "Person", "description": "Employee"},
                {"name": "Acme Corp", "type": "Organization", "description": "Company"},
            ],
            "relationships": [
                {
                    "source": "John",
                    "target": "Acme Corp",
                    "type": "WORKS_AT",
                    "description": "Employment",
                },
            ],
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = extraction_json
        mock_llm.complete.return_value = mock_response

        entity_id_1 = uuid.uuid4()
        entity_id_2 = uuid.uuid4()

        # Mock batch_create_entities returning entity map
        mock_graph.batch_create_entities.return_value = (
            2,
            {"john": entity_id_1, "acme corp": entity_id_2},
        )
        mock_graph.batch_create_relationships.return_value = 1

        result = await builder.build_from_chunks(chunks, doc_id)

        assert result["entities_created"] == 2
        assert result["relationships_created"] == 1
        mock_graph.batch_create_entities.assert_awaited_once()
        mock_graph.batch_create_relationships.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_deduplicates_entities(
        self, builder: KGBuilder, mock_graph: AsyncMock, mock_llm: AsyncMock
    ) -> None:
        """Same entity across multiple chunks should be created once."""
        doc_id = uuid.uuid4()
        chunks = [
            {"id": uuid.uuid4(), "content": "John works at Acme.", "metadata": {}},
            {"id": uuid.uuid4(), "content": "John lives in NYC.", "metadata": {}},
        ]

        extraction = json.dumps({
            "entities": [
                {"name": "John", "type": "Person"},
            ],
            "relationships": [],
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = extraction
        mock_llm.complete.return_value = mock_response

        mock_graph.batch_create_entities.return_value = (
            1,
            {"john": uuid.uuid4()},
        )
        mock_graph.batch_create_relationships.return_value = 0

        result = await builder.build_from_chunks(chunks, doc_id)

        # Entity "John:Person" should only appear once in the batch
        assert result["entities_created"] == 1
        entities_arg = mock_graph.batch_create_entities.call_args[0][0]
        assert len(entities_arg) == 1

    @pytest.mark.asyncio
    async def test_build_handles_llm_failure(
        self, builder: KGBuilder, mock_graph: AsyncMock, mock_llm: AsyncMock
    ) -> None:
        chunks = [
            {"id": uuid.uuid4(), "content": "Test content", "metadata": {}},
        ]

        mock_llm.complete.side_effect = Exception("LLM timeout")

        mock_graph.batch_create_entities.return_value = (0, {})
        mock_graph.batch_create_relationships.return_value = 0

        result = await builder.build_from_chunks(chunks, uuid.uuid4())
        assert result["entities_created"] == 0
        assert result["relationships_created"] == 0
