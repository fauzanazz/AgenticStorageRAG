"""Vector search tool for the RAG agent.

Searches document embeddings via pgvector for semantically similar content.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.agents.interfaces import IAgentTool
from app.domain.knowledge.interfaces import IVectorService
from app.domain.knowledge.schemas import VectorSearchRequest

logger = logging.getLogger(__name__)


class VectorSearchTool(IAgentTool):
    """Search document embeddings for semantically similar content.

    The agent uses this for open-ended questions, fact retrieval,
    or when it needs raw document context.
    """

    def __init__(self, vector_service: IVectorService) -> None:
        self._vector = vector_service

    @property
    def name(self) -> str:
        return "vector_search"

    @property
    def description(self) -> str:
        return (
            "Search document chunks by semantic similarity. "
            "Use when the query needs factual information from documents, "
            "or when you need context to answer a question. "
            "Input: query (str), top_k (int, default 10), document_id (optional UUID)"
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute vector similarity search.

        Args:
            query: Search query string.
            top_k: Number of results (default 10).
            document_id: Optional filter by document.
        """
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 10)
        document_id = kwargs.get("document_id")

        if not query:
            return {"result": [], "error": "No query provided"}

        try:
            results = await self._vector.search(
                VectorSearchRequest(
                    query=query,
                    top_k=top_k,
                    document_id=document_id,
                    similarity_threshold=0.5,
                )
            )

            formatted = []
            for r in results:
                entry = {
                    "content": r.content,
                    "document_id": str(r.document_id),
                    "chunk_id": str(r.chunk_id),
                    "similarity": r.similarity,
                    "metadata": r.metadata,
                }
                formatted.append(entry)

            return {
                "result": formatted,
                "count": len(formatted),
                "source": "vector_search",
            }

        except Exception as e:
            logger.error("Vector search tool failed: %s", e)
            return {"result": [], "error": str(e)}
