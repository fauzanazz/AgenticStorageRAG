"""Hybrid search tool for the RAG agent.

Combines graph and vector search for comprehensive retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.agents.interfaces import IAgentTool
from app.domain.knowledge.interfaces import IHybridRetriever
from app.domain.knowledge.schemas import HybridSearchRequest

logger = logging.getLogger(__name__)


class HybridSearchTool(IAgentTool):
    """Combined graph + vector search for comprehensive retrieval.

    The agent uses this as its primary retrieval tool when it needs
    both structured (graph) and unstructured (vector) context.
    """

    def __init__(self, hybrid_retriever: IHybridRetriever) -> None:
        self._retriever = hybrid_retriever

    @property
    def name(self) -> str:
        return "hybrid_search"

    @property
    def description(self) -> str:
        return (
            "Combined search across knowledge graph AND document embeddings. "
            "This is the most comprehensive search tool. Use as the primary "
            "retrieval method for most questions. Combines structured entity/relationship "
            "knowledge with raw document context. "
            "Input: query (str), top_k (int, default 10), vector_weight (float 0-1, default 0.5)"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query combining graph and vector retrieval.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return (default 10).",
                },
                "vector_weight": {
                    "type": "number",
                    "description": "Weight for vector results vs graph (0.0–1.0, default 0.5).",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute hybrid search.

        Args:
            query: Search query string.
            top_k: Number of results (default 10).
            vector_weight: Balance between vector and graph (default 0.5).
        """
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 10)
        vector_weight = kwargs.get("vector_weight", 0.5)

        if not query:
            return {"result": [], "error": "No query provided"}

        try:
            results = await self._retriever.search(
                HybridSearchRequest(
                    query=query,
                    top_k=top_k,
                    vector_weight=vector_weight,
                )
            )

            formatted = []
            for r in results:
                entry = {
                    "content": r.content,
                    "source": r.source,
                    "score": r.score,
                    "document_id": str(r.document_id) if r.document_id else None,
                    "chunk_id": str(r.chunk_id) if r.chunk_id else None,
                    "entity_id": str(r.entity_id) if r.entity_id else None,
                    "metadata": r.metadata,
                }
                formatted.append(entry)

            return {
                "result": formatted,
                "count": len(formatted),
                "source": "hybrid",
            }

        except Exception as e:
            logger.error("Hybrid search tool failed: %s", e)
            return {"result": [], "error": str(e)}
