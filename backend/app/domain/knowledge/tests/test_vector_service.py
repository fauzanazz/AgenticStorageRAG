"""Tests for vector service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.knowledge.vector_service import VectorService, _estimate_tokens
from app.domain.knowledge.exceptions import EmbeddingError
from app.domain.knowledge.schemas import VectorSearchRequest


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> VectorService:
    return VectorService(db=mock_db)


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 0

    def test_short_string(self) -> None:
        assert _estimate_tokens("hello") == 1

    def test_longer_string(self) -> None:
        text = "This is a longer piece of text for testing"
        assert _estimate_tokens(text) == len(text) // 4


class TestEmbedChunks:
    """Tests for embedding generation and storage."""

    @pytest.mark.asyncio
    async def test_empty_chunks(self, service: VectorService) -> None:
        result = await service.embed_chunks([], uuid.uuid4())
        assert result == 0

    @pytest.mark.asyncio
    async def test_embed_chunks_success(
        self, service: VectorService, mock_db: AsyncMock
    ) -> None:
        doc_id = uuid.uuid4()
        chunks = [
            {"id": uuid.uuid4(), "content": "Test chunk 1", "metadata": {"page": 1}},
            {"id": uuid.uuid4(), "content": "Test chunk 2", "metadata": {"page": 2}},
        ]

        # Mock LiteLLM embedding response
        mock_response = MagicMock()
        mock_response.data = [
            {"embedding": [0.1] * 1536},
            {"embedding": [0.2] * 1536},
        ]

        with patch("app.domain.knowledge.vector_service.litellm.aembedding", return_value=mock_response):
            result = await service.embed_chunks(chunks, doc_id)

        assert result == 2
        assert mock_db.add.call_count == 2
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_chunks_api_failure(
        self, service: VectorService
    ) -> None:
        chunks = [
            {"id": uuid.uuid4(), "content": "Test chunk", "metadata": None},
        ]

        with patch(
            "app.domain.knowledge.vector_service.litellm.aembedding",
            side_effect=Exception("API rate limit"),
        ):
            with pytest.raises(EmbeddingError, match="Failed to embed chunks"):
                await service.embed_chunks(chunks, uuid.uuid4())


class TestVectorSearch:
    """Tests for vector similarity search."""

    @pytest.mark.asyncio
    async def test_search_success(
        self, service: VectorService, mock_db: AsyncMock
    ) -> None:
        chunk_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        mock_row = MagicMock()
        mock_row.chunk_id = chunk_id
        mock_row.document_id = doc_id
        mock_row.content = "Test content"
        mock_row.similarity = 0.95
        mock_row.metadata_json = '{"page": 1}'

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 1536}]

        with patch(
            "app.domain.knowledge.vector_service.litellm.aembedding",
            return_value=mock_response,
        ):
            results = await service.search(
                VectorSearchRequest(query="test query", top_k=5)
            )

        assert len(results) == 1
        assert results[0].content == "Test content"
        assert results[0].similarity == 0.95

    @pytest.mark.asyncio
    async def test_search_with_document_filter(
        self, service: VectorService, mock_db: AsyncMock
    ) -> None:
        doc_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 1536}]

        with patch(
            "app.domain.knowledge.vector_service.litellm.aembedding",
            return_value=mock_response,
        ):
            results = await service.search(
                VectorSearchRequest(query="test", document_id=doc_id)
            )

        assert results == []


class TestDeleteDocumentEmbeddings:
    """Tests for deleting document embeddings."""

    @pytest.mark.asyncio
    async def test_delete_embeddings(
        self, service: VectorService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        count = await service.delete_document_embeddings(uuid.uuid4())
        assert count == 5
