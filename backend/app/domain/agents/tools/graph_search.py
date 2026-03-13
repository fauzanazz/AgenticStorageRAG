"""Graph search tool for the RAG agent.

Searches the Neo4j knowledge graph for entities and relationships
matching the query.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.agents.interfaces import IAgentTool
from app.domain.knowledge.interfaces import IGraphService
from app.domain.knowledge.schemas import GraphSearchRequest

logger = logging.getLogger(__name__)


class GraphSearchTool(IAgentTool):
    """Search the knowledge graph for entities and their relationships.

    The agent uses this when the query involves structured knowledge,
    entity lookups, or relationship traversal.
    """

    def __init__(self, graph_service: IGraphService) -> None:
        self._graph = graph_service

    @property
    def name(self) -> str:
        return "graph_search"

    @property
    def description(self) -> str:
        return (
            "Search the knowledge graph for entities and relationships. "
            "Use when the query asks about specific entities, their properties, "
            "or how entities are related to each other. "
            "Input: query (str), entity_types (optional list[str]), max_depth (int, default 2)"
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute graph search.

        Args:
            query: Search query string.
            entity_types: Optional filter by entity types.
            max_depth: Max traversal depth (default 2).
            top_k: Number of results (default 10).
        """
        query = kwargs.get("query", "")
        entity_types = kwargs.get("entity_types")
        max_depth = kwargs.get("max_depth", 2)
        top_k = kwargs.get("top_k", 10)

        if not query:
            return {"result": [], "error": "No query provided"}

        try:
            results = await self._graph.search_entities(
                GraphSearchRequest(
                    query=query,
                    entity_types=entity_types,
                    max_depth=max_depth,
                    top_k=top_k,
                )
            )

            formatted = []
            for r in results:
                entry = {
                    "entity_name": r.entity.name,
                    "entity_type": r.entity.entity_type,
                    "description": r.entity.description,
                    "relevance": r.relevance_score,
                    "relationships": [
                        {
                            "type": rel.relationship_type,
                            "target": rel.target_entity_name,
                        }
                        for rel in r.relationships[:5]
                    ],
                }
                formatted.append(entry)

            return {
                "result": formatted,
                "count": len(formatted),
                "source": "knowledge_graph",
            }

        except Exception as e:
            logger.error("Graph search tool failed: %s", e)
            return {"result": [], "error": str(e)}
