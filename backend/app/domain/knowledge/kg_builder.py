"""Knowledge graph builder using LLM extraction.

Uses LLM to extract entities and relationships from document chunks,
then populates the Neo4j graph and PostgreSQL shadow records.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import uuid
from typing import Any

from app.domain.knowledge.exceptions import GraphBuildError
from app.domain.knowledge.interfaces import IGraphService, IKGBuilder
from app.domain.knowledge.schemas import EntityCreate, RelationshipCreate
from app.infra.llm import LLMProvider

logger = logging.getLogger(__name__)

# Concurrent chunk extraction limit (avoid overwhelming the LLM API)
_KG_CONCURRENCY = 2

# Process chunks in batches of this size to limit memory accumulation
# from LiteLLM HTTP response caching and asyncio coroutine frames.
_KG_BATCH_SIZE = 20

# Prompt for entity/relationship extraction
EXTRACTION_SYSTEM_PROMPT = """You are a knowledge graph extraction expert. Given a text chunk, extract entities and relationships.

Output ONLY valid JSON with this exact structure:
{
    "entities": [
        {
            "name": "Entity Name",
            "type": "EntityType",
            "description": "Brief description"
        }
    ],
    "relationships": [
        {
            "source": "Source Entity Name",
            "target": "Target Entity Name",
            "type": "RELATIONSHIP_TYPE",
            "description": "Brief description of the relationship"
        }
    ]
}

Rules:
- Entity types should be capitalized singular nouns (Person, Organization, Concept, Technology, Event, Location, etc.)
- Relationship types should be UPPER_SNAKE_CASE (WORKS_AT, RELATED_TO, DEPENDS_ON, etc.)
- Extract meaningful entities, not every noun
- Include relationships that connect the extracted entities
- If no entities or relationships found, return empty arrays
- Be consistent with entity naming across chunks"""


class KGBuilder(IKGBuilder):
    """Builds knowledge graph from document chunks using LLM extraction.

    Flow:
    1. Send each chunk to LLM for entity/relationship extraction
    2. Deduplicate entities by name + type
    3. Create entities in graph (batch Neo4j + bulk PG)
    4. Create relationships between entities (batch Neo4j + bulk PG)
    """

    def __init__(
        self,
        graph_service: IGraphService,
        llm: LLMProvider,
    ) -> None:
        self._graph = graph_service
        self._llm = llm

    async def build_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        document_id: uuid.UUID,
    ) -> dict[str, int]:
        """Extract entities and relationships from chunks and add to graph."""
        if not chunks:
            return {"entities_created": 0, "relationships_created": 0}

        all_entities: dict[str, EntityCreate] = {}  # name:type -> entity
        all_relationships: list[dict[str, str]] = []

        # Extract from chunks in batches to limit memory accumulation.
        # LiteLLM HTTP response objects and asyncio coroutine frames
        # grow unbounded with asyncio.gather(*all_500_coroutines).
        semaphore = asyncio.Semaphore(_KG_CONCURRENCY)
        total = len(chunks)

        async def _extract_one(i: int, chunk: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await self._extract_from_chunk(chunk["content"])
                except Exception as e:
                    logger.warning("Failed to extract from chunk %d: %s", i, e)
                    return None

        for batch_start in range(0, total, _KG_BATCH_SIZE):
            batch_end = min(batch_start + _KG_BATCH_SIZE, total)
            batch = chunks[batch_start:batch_end]

            extractions = await asyncio.gather(
                *[
                    _extract_one(batch_start + j, chunk)
                    for j, chunk in enumerate(batch)
                ],
                return_exceptions=False,
            )

            for j, extraction in enumerate(extractions):
                if not extraction:
                    continue
                chunk_idx = batch_start + j

                # Collect entities (deduplicate by name:type key)
                for ent in extraction.get("entities", []):
                    try:
                        key = f"{ent['name'].lower()}:{ent['type'].lower()}"
                        if key not in all_entities:
                            all_entities[key] = EntityCreate(
                                name=ent["name"],
                                entity_type=ent["type"],
                                description=ent.get("description"),
                                source_document_id=document_id,
                            )
                    except (KeyError, AttributeError) as e:
                        logger.warning("Malformed entity in chunk %d: %s", chunk_idx, e)

                # Collect relationships
                for rel in extraction.get("relationships", []):
                    all_relationships.append(rel)

                logger.debug(
                    "Extracted from chunk %d/%d: %d entities, %d relationships",
                    chunk_idx + 1,
                    total,
                    len(extraction.get("entities", [])),
                    len(extraction.get("relationships", [])),
                )

            # Free LLM response objects accumulated during this batch
            del extractions
            gc.collect()

            logger.debug(
                "KG extraction batch %d-%d/%d complete",
                batch_start + 1, batch_end, total,
            )

        # Batch-create entities and relationships
        entities_created, entity_map = await self._graph.batch_create_entities(
            list(all_entities.values()),
        )

        relationships_created = await self._graph.batch_create_relationships(
            all_relationships, entity_map, document_id,
        )

        logger.info(
            "KG built for document %s: %d entities, %d relationships",
            document_id,
            entities_created,
            relationships_created,
        )

        return {
            "entities_created": entities_created,
            "relationships_created": relationships_created,
        }

    async def _extract_from_chunk(
        self, content: str
    ) -> dict[str, Any] | None:
        """Use LLM to extract entities and relationships from a text chunk."""
        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Extract entities and relationships from this text:\n\n{content}",
                    },
                ],
                temperature=0.0,
                max_tokens=2000,
            )

            # Parse the response
            content_str = response.choices[0].message.content
            if not content_str:
                return None

            # Try to extract JSON from the response
            result = _parse_json_response(content_str)
            return result

        except Exception as e:
            logger.warning("LLM extraction failed: %s", e)
            return None


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        try:
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        try:
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Try finding JSON object in text
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end])
        except json.JSONDecodeError:
            pass

    return None
