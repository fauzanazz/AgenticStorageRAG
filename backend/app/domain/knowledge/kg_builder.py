"""Knowledge graph builder using LLM extraction.

Uses LLM to extract entities and relationships from document chunks,
then populates the Neo4j graph and PostgreSQL shadow records.
"""

from __future__ import annotations

import asyncio
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
_KG_CONCURRENCY = 5

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
    3. Create entities in graph
    4. Create relationships between entities
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

        # Extract from all chunks concurrently (bounded by semaphore)
        semaphore = asyncio.Semaphore(_KG_CONCURRENCY)

        async def _extract_one(i: int, chunk: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await self._extract_from_chunk(chunk["content"])
                except Exception as e:
                    logger.warning("Failed to extract from chunk %d: %s", i, e)
                    return None

        extractions = await asyncio.gather(
            *[_extract_one(i, chunk) for i, chunk in enumerate(chunks)],
            return_exceptions=False,
        )

        for i, extraction in enumerate(extractions):
            if not extraction:
                continue

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
                    logger.warning("Malformed entity in chunk %d: %s", i, e)

            # Collect relationships
            for rel in extraction.get("relationships", []):
                all_relationships.append(rel)

            logger.debug(
                "Extracted from chunk %d/%d: %d entities, %d relationships",
                i + 1,
                len(chunks),
                len(extraction.get("entities", [])),
                len(extraction.get("relationships", [])),
            )

        # Create entities in graph
        entity_map: dict[str, uuid.UUID] = {}  # name_lower -> entity ID
        entities_created = 0

        for entity_create in all_entities.values():
            try:
                entity_resp = await self._graph.create_entity(entity_create)
                entity_map[entity_create.name.lower()] = entity_resp.id
                entities_created += 1
            except Exception as e:
                logger.warning(
                    "Failed to create entity '%s': %s",
                    entity_create.name,
                    e,
                )

        # Create relationships
        relationships_created = 0
        for rel in all_relationships:
            source_name = rel.get("source", "").lower()
            target_name = rel.get("target", "").lower()

            source_id = entity_map.get(source_name)
            target_id = entity_map.get(target_name)

            if source_id and target_id and source_id != target_id:
                try:
                    await self._graph.create_relationship(
                        RelationshipCreate(
                            source_entity_id=source_id,
                            target_entity_id=target_id,
                            relationship_type=rel.get("type", "RELATED_TO"),
                            properties=(
                                {"description": rel["description"]}
                                if rel.get("description")
                                else None
                            ),
                            source_document_id=document_id,
                        )
                    )
                    relationships_created += 1
                except Exception as e:
                    logger.warning(
                        "Failed to create relationship %s->%s: %s",
                        rel.get("source"),
                        rel.get("target"),
                        e,
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
