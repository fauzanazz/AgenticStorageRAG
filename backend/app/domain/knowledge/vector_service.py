"""pgvector service implementation.

Handles embedding generation via LiteLLM and vector similarity
search using PostgreSQL with pgvector extension.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import litellm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.knowledge.exceptions import EmbeddingError
from app.domain.knowledge.interfaces import IVectorService
from app.domain.knowledge.models import DocumentEmbedding
from app.domain.knowledge.schemas import VectorSearchRequest, VectorSearchResult

logger = logging.getLogger(__name__)

# Fallback embedding model (used when no config value is available)
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100  # Max chunks per embedding API call


def _get_embedding_model() -> str:
    """Return the configured embedding model (defaults to text-embedding-3-small)."""
    return get_settings().embedding_model or _DEFAULT_EMBEDDING_MODEL


class VectorService(IVectorService):
    """Vector embedding service using pgvector + LiteLLM embeddings.

    Generates embeddings via LiteLLM and stores them in PostgreSQL with
    pgvector for similarity search. The embedding model is configured via
    the ``EMBEDDING_MODEL`` environment variable (default: text-embedding-3-small).
    To use Gemini embeddings set ``EMBEDDING_MODEL=gemini/text-embedding-004``
    and provide ``GEMINI_API_KEY``.
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_model: str | None = None,
    ) -> None:
        self._db = db
        self._embedding_model = embedding_model or _get_embedding_model()

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
        if not chunks:
            return 0

        total_created = 0

        # Process in batches
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            texts = [chunk["content"] for chunk in batch]

            try:
                # Generate embeddings via LiteLLM
                embeddings = await self._generate_embeddings(texts)

                # Store embeddings
                for j, chunk in enumerate(batch):
                    embedding_record = DocumentEmbedding(
                        chunk_id=chunk["id"],
                        document_id=document_id,
                        content=chunk["content"],
                        embedding=embeddings[j],
                        embedding_model=self._embedding_model,
                        token_count=_estimate_tokens(chunk["content"]),
                        metadata_json=(
                            json.dumps(chunk["metadata"]) if chunk.get("metadata") else None
                        ),
                    )
                    self._db.add(embedding_record)

                await self._db.flush()
                total_created += len(batch)

                logger.info(
                    "Embedded batch %d-%d of %d chunks for document %s",
                    i + 1,
                    min(i + BATCH_SIZE, len(chunks)),
                    len(chunks),
                    document_id,
                )

            except Exception as e:
                logger.error("Embedding batch %d failed: %s", i, e)
                raise EmbeddingError(f"Failed to embed chunks: {e}") from e

        return total_created

    async def search(self, request: VectorSearchRequest) -> list[VectorSearchResult]:
        """Search by vector similarity using pgvector.

        Uses cosine distance for similarity ranking.
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embeddings([request.query])
            if not query_embedding:
                return []

            embedding_vector = query_embedding[0]

            # Format as pgvector literal: '[0.1,0.2,...]'
            vec_literal = "[" + ",".join(str(v) for v in embedding_vector) + "]"

            # Build pgvector similarity query
            # Uses cosine distance: 1 - (a <=> b) gives cosine similarity
            # The embedding column is ARRAY(Float) so we cast both sides to vector
            query_parts = [
                r"""
                SELECT
                    id, chunk_id, document_id, content, metadata_json,
                    1 - (embedding\:\:vector <=> :query_vec\:\:vector) AS similarity
                FROM document_embeddings
                WHERE embedding IS NOT NULL
                """
            ]
            params: dict[str, Any] = {
                "query_vec": vec_literal,
                "top_k": request.top_k,
                "threshold": request.similarity_threshold,
            }

            if request.document_id:
                query_parts.append("AND document_id = :doc_id")
                params["doc_id"] = str(request.document_id)

            query_parts.append(
                r"AND 1 - (embedding\:\:vector <=> :query_vec\:\:vector) >= :threshold"
            )
            query_parts.append(r"ORDER BY embedding\:\:vector <=> :query_vec\:\:vector")
            query_parts.append("LIMIT :top_k")

            full_query = "\n".join(query_parts)
            result = await self._db.execute(text(full_query), params)
            rows = result.fetchall()

            return [
                VectorSearchResult(
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    content=row.content,
                    similarity=float(row.similarity),
                    metadata=(json.loads(row.metadata_json) if row.metadata_json else None),
                )
                for row in rows
            ]

        except Exception as e:
            logger.error("Vector search failed: %s", e)
            await self._db.rollback()
            raise EmbeddingError(f"Vector search failed: {e}") from e

    async def delete_document_embeddings(self, document_id: uuid.UUID) -> int:
        """Delete all embeddings for a document."""
        result = await self._db.execute(
            text("DELETE FROM document_embeddings WHERE document_id = :doc_id"),
            {"doc_id": str(document_id)},
        )
        await self._db.flush()
        count = result.rowcount or 0
        logger.info("Deleted %d embeddings for document %s", count, document_id)
        return count

    async def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using LiteLLM.

        Uses the model configured by the EMBEDDING_MODEL setting.
        Supports any provider that LiteLLM supports, including OpenAI,
        Google Gemini (``gemini/text-embedding-004``), and DashScope.

        Retries up to 3 times with exponential backoff (1s, 2s) on failure.
        """
        max_attempts = 3
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = await litellm.aembedding(
                    model=self._embedding_model,
                    input=texts,
                )
                return [item["embedding"] for item in response.data]

            except Exception as e:
                last_exc = e
                if attempt < max_attempts:
                    wait = 2 ** (attempt - 1)  # 1s, 2s
                    logger.warning(
                        "Embedding generation attempt %d/%d failed: %s. Retrying in %ds...",
                        attempt,
                        max_attempts,
                        e,
                        wait,
                    )
                    await asyncio.sleep(wait)

        logger.error(
            "Embedding generation failed after %d attempts: %s",
            max_attempts,
            last_exc,
        )
        raise EmbeddingError(
            f"Failed to generate embeddings after {max_attempts} attempts: {last_exc}"
        ) from last_exc


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (4 chars per token average)."""
    return len(text) // 4
