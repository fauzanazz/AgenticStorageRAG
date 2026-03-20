"""Neo4j graph service implementation.

Handles entity/relationship CRUD and graph traversal queries
against the Neo4j knowledge graph database.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.knowledge.exceptions import (
    EntityNotFoundError,
    GraphBuildError,
    GraphQueryError,
    RelationshipNotFoundError,
)
from app.domain.knowledge.interfaces import IGraphService
from app.domain.knowledge.models import KnowledgeEntity, KnowledgeRelationship
from app.domain.knowledge.schemas import (
    EntityCreate,
    EntityResponse,
    EntityWithRelationships,
    GraphEdge,
    GraphNode,
    GraphSearchRequest,
    GraphSearchResult,
    GraphVisualization,
    KnowledgeStats,
    RelationshipCreate,
    RelationshipResponse,
)
from app.infra.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class GraphService(IGraphService):
    """Knowledge graph service using Neo4j + PostgreSQL shadow records.

    Entities and relationships are stored in both Neo4j (for graph queries)
    and PostgreSQL (for SQL joins with document data).
    """

    def __init__(self, db: AsyncSession, neo4j: Neo4jClient) -> None:
        self._db = db
        self._neo4j = neo4j

    async def create_entity(self, entity: EntityCreate) -> EntityResponse:
        """Create an entity in both Neo4j and PostgreSQL."""
        try:
            # Create in Neo4j
            neo4j_id = str(uuid.uuid4())
            properties = {
                "neo4j_id": neo4j_id,
                "name": entity.name,
                "entity_type": entity.entity_type,
            }
            if entity.description:
                properties["description"] = entity.description
            if entity.properties:
                properties["properties_json"] = json.dumps(entity.properties)

            await self._neo4j.execute_write(
                f"CREATE (n:Entity:{_sanitize_label(entity.entity_type)} $props) RETURN n",
                {"props": properties},
            )

            # Create shadow record in PostgreSQL
            db_entity = KnowledgeEntity(
                neo4j_id=neo4j_id,
                entity_type=entity.entity_type,
                name=entity.name,
                description=entity.description,
                properties_json=json.dumps(entity.properties) if entity.properties else None,
                source_document_id=entity.source_document_id,
            )
            self._db.add(db_entity)
            await self._db.flush()
            await self._db.refresh(db_entity)

            return EntityResponse(
                id=db_entity.id,
                neo4j_id=neo4j_id,
                entity_type=db_entity.entity_type,
                name=db_entity.name,
                description=db_entity.description,
                properties=entity.properties,
                source_document_id=db_entity.source_document_id,
                created_at=db_entity.created_at,
                updated_at=db_entity.updated_at,
                relationship_count=0,
            )

        except Exception as e:
            logger.error("Failed to create entity: %s", e)
            raise GraphBuildError(f"Failed to create entity '{entity.name}': {e}") from e

    async def get_entity(self, entity_id: uuid.UUID) -> EntityWithRelationships:
        """Get entity with its relationships."""
        stmt = select(KnowledgeEntity).where(KnowledgeEntity.id == entity_id)
        result = await self._db.execute(stmt)
        entity = result.scalar_one_or_none()

        if not entity:
            raise EntityNotFoundError(str(entity_id))

        # Get relationships from Neo4j
        relationships = await self._get_entity_relationships(entity.neo4j_id)

        properties = json.loads(entity.properties_json) if entity.properties_json else None

        return EntityWithRelationships(
            id=entity.id,
            neo4j_id=entity.neo4j_id,
            entity_type=entity.entity_type,
            name=entity.name,
            description=entity.description,
            properties=properties,
            source_document_id=entity.source_document_id,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            relationship_count=len(relationships),
            relationships=relationships,
        )

    async def search_entities(
        self, request: GraphSearchRequest
    ) -> list[GraphSearchResult]:
        """Search entities using Neo4j full-text or pattern matching."""
        try:
            # Use Neo4j for graph-aware search
            type_filter = ""
            if request.entity_types:
                labels = " OR ".join(
                    f"n:{_sanitize_label(t)}" for t in request.entity_types
                )
                type_filter = f"AND ({labels})"

            cypher = f"""
                MATCH (n)
                WHERE (n.name CONTAINS $search_term OR n.description CONTAINS $search_term)
                {type_filter}
                WITH n,
                     CASE WHEN n.name CONTAINS $search_term THEN 2 ELSE 1 END AS score
                ORDER BY score DESC
                LIMIT $limit
                OPTIONAL MATCH (n)-[r]-(m)
                RETURN n, collect(DISTINCT {{rel: type(r), target: m.name, target_type: m.entity_type}}) AS rels
            """

            records = await self._neo4j.execute_read(
                cypher,
                {"search_term": request.query, "limit": request.top_k},
            )

            results = []
            for record in records:
                node = record["n"]
                neo4j_id = node.get("neo4j_id", "")

                # Look up PostgreSQL entity
                stmt = select(KnowledgeEntity).where(
                    KnowledgeEntity.neo4j_id == neo4j_id
                )
                db_result = await self._db.execute(stmt)
                db_entity = db_result.scalar_one_or_none()

                if db_entity:
                    properties = (
                        json.loads(db_entity.properties_json)
                        if db_entity.properties_json
                        else None
                    )
                    entity_resp = EntityResponse(
                        id=db_entity.id,
                        neo4j_id=db_entity.neo4j_id,
                        entity_type=db_entity.entity_type,
                        name=db_entity.name,
                        description=db_entity.description,
                        properties=properties,
                        source_document_id=db_entity.source_document_id,
                        created_at=db_entity.created_at,
                        updated_at=db_entity.updated_at,
                    )

                    rels_data = record.get("rels", [])
                    rel_responses = []
                    for rel in rels_data:
                        if rel.get("rel"):
                            rel_responses.append(
                                RelationshipResponse(
                                    id=uuid.uuid4(),
                                    neo4j_id="",
                                    relationship_type=rel["rel"],
                                    source_entity_id=db_entity.id,
                                    target_entity_id=db_entity.id,
                                    source_entity_name=db_entity.name,
                                    target_entity_name=rel.get("target", ""),
                                    created_at=db_entity.created_at,
                                )
                            )

                    results.append(
                        GraphSearchResult(
                            entity=entity_resp,
                            relationships=rel_responses,
                            relevance_score=1.0,
                        )
                    )

            return results

        except Exception as e:
            logger.error("Graph search failed: %s", e)
            raise GraphQueryError(f"Graph search failed: {e}") from e

    async def create_relationship(
        self, relationship: RelationshipCreate
    ) -> RelationshipResponse:
        """Create a relationship in both Neo4j and PostgreSQL."""
        try:
            # Get source and target entities
            source = await self._db.get(KnowledgeEntity, relationship.source_entity_id)
            target = await self._db.get(KnowledgeEntity, relationship.target_entity_id)

            if not source:
                raise EntityNotFoundError(str(relationship.source_entity_id))
            if not target:
                raise EntityNotFoundError(str(relationship.target_entity_id))

            # Create in Neo4j
            neo4j_id = str(uuid.uuid4())
            rel_type = _sanitize_label(relationship.relationship_type)

            props: dict[str, Any] = {
                "neo4j_id": neo4j_id,
                "weight": relationship.weight,
            }
            if relationship.properties:
                props["properties_json"] = json.dumps(relationship.properties)

            await self._neo4j.execute_write(
                f"""
                MATCH (a {{neo4j_id: $source_id}}), (b {{neo4j_id: $target_id}})
                CREATE (a)-[r:{rel_type} $props]->(b)
                RETURN r
                """,
                {
                    "source_id": source.neo4j_id,
                    "target_id": target.neo4j_id,
                    "props": props,
                },
            )

            # Create shadow record
            db_rel = KnowledgeRelationship(
                neo4j_id=neo4j_id,
                relationship_type=relationship.relationship_type,
                source_entity_id=relationship.source_entity_id,
                target_entity_id=relationship.target_entity_id,
                properties_json=(
                    json.dumps(relationship.properties)
                    if relationship.properties
                    else None
                ),
                weight=relationship.weight,
                source_document_id=relationship.source_document_id,
            )
            self._db.add(db_rel)
            await self._db.flush()
            await self._db.refresh(db_rel)

            return RelationshipResponse(
                id=db_rel.id,
                neo4j_id=neo4j_id,
                relationship_type=db_rel.relationship_type,
                source_entity_id=db_rel.source_entity_id,
                target_entity_id=db_rel.target_entity_id,
                source_entity_name=source.name,
                target_entity_name=target.name,
                properties=relationship.properties,
                weight=db_rel.weight,
                source_document_id=db_rel.source_document_id,
                created_at=db_rel.created_at,
            )

        except EntityNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to create relationship: %s", e)
            raise GraphBuildError(f"Failed to create relationship: {e}") from e

    async def batch_create_entities(
        self,
        entities: list[EntityCreate],
    ) -> tuple[int, dict[str, uuid.UUID]]:
        """Create entities in bulk: single Neo4j transaction + batched PG inserts.

        Returns (count_created, name_lower -> entity_id map).
        """
        if not entities:
            return 0, {}

        entity_map: dict[str, uuid.UUID] = {}
        neo4j_queries: list[tuple[str, dict[str, Any]]] = []
        pg_objects: list[KnowledgeEntity] = []

        for entity in entities:
            neo4j_id = str(uuid.uuid4())
            properties: dict[str, Any] = {
                "neo4j_id": neo4j_id,
                "name": entity.name,
                "entity_type": entity.entity_type,
            }
            if entity.description:
                properties["description"] = entity.description
            if entity.properties:
                properties["properties_json"] = json.dumps(entity.properties)

            label = _sanitize_label(entity.entity_type)
            neo4j_queries.append((
                f"CREATE (n:Entity:{label} $props) RETURN n",
                {"props": properties},
            ))

            db_entity = KnowledgeEntity(
                neo4j_id=neo4j_id,
                entity_type=entity.entity_type,
                name=entity.name,
                description=entity.description,
                properties_json=json.dumps(entity.properties) if entity.properties else None,
                source_document_id=entity.source_document_id,
            )
            pg_objects.append(db_entity)

        # Batch Neo4j write (single transaction)
        try:
            await self._neo4j.execute_write_batch(neo4j_queries)
        except Exception as e:
            logger.error("Batch Neo4j entity creation failed: %s", e)
            return 0, {}

        # Batch PG insert
        for obj in pg_objects:
            self._db.add(obj)
        await self._db.flush()

        # Build map from flushed objects (now have IDs)
        for obj in pg_objects:
            entity_map[obj.name.lower()] = obj.id

        logger.info("Batch-created %d entities", len(pg_objects))
        return len(pg_objects), entity_map

    async def batch_create_relationships(
        self,
        raw_relationships: list[dict[str, str]],
        entity_map: dict[str, uuid.UUID],
        document_id: uuid.UUID,
    ) -> int:
        """Create relationships in bulk: single Neo4j transaction + batched PG inserts.

        Returns count of relationships created.
        """
        if not raw_relationships or not entity_map:
            return 0

        # Resolve entity names to IDs and neo4j_ids, filtering unresolvable
        # We need the neo4j_id for each entity to create Neo4j relationships
        entity_ids = list(set(entity_map.values()))
        if not entity_ids:
            return 0

        # Fetch neo4j_ids for all entities in one query
        from sqlalchemy import select as sa_select
        result = await self._db.execute(
            sa_select(KnowledgeEntity.id, KnowledgeEntity.neo4j_id, KnowledgeEntity.name)
            .where(KnowledgeEntity.id.in_(entity_ids))
        )
        rows = result.all()
        id_to_neo4j: dict[uuid.UUID, str] = {r[0]: r[1] for r in rows}

        neo4j_queries: list[tuple[str, dict[str, Any]]] = []
        pg_objects: list[KnowledgeRelationship] = []

        for rel in raw_relationships:
            source_name = rel.get("source", "").lower()
            target_name = rel.get("target", "").lower()

            source_id = entity_map.get(source_name)
            target_id = entity_map.get(target_name)

            if not source_id or not target_id or source_id == target_id:
                continue

            source_neo4j = id_to_neo4j.get(source_id)
            target_neo4j = id_to_neo4j.get(target_id)
            if not source_neo4j or not target_neo4j:
                continue

            neo4j_id = str(uuid.uuid4())
            rel_type = _sanitize_label(rel.get("type", "RELATED_TO"))
            props: dict[str, Any] = {"neo4j_id": neo4j_id, "weight": 1.0}
            if rel.get("description"):
                props["properties_json"] = json.dumps({"description": rel["description"]})

            neo4j_queries.append((
                f"""
                MATCH (a {{neo4j_id: $source_id}}), (b {{neo4j_id: $target_id}})
                CREATE (a)-[r:{rel_type} $props]->(b)
                RETURN r
                """,
                {
                    "source_id": source_neo4j,
                    "target_id": target_neo4j,
                    "props": props,
                },
            ))

            rel_properties = {"description": rel["description"]} if rel.get("description") else None
            db_rel = KnowledgeRelationship(
                neo4j_id=neo4j_id,
                relationship_type=rel.get("type", "RELATED_TO"),
                source_entity_id=source_id,
                target_entity_id=target_id,
                properties_json=json.dumps(rel_properties) if rel_properties else None,
                weight=1.0,
                source_document_id=document_id,
            )
            pg_objects.append(db_rel)

        if not neo4j_queries:
            return 0

        # Batch Neo4j write (single transaction)
        try:
            await self._neo4j.execute_write_batch(neo4j_queries)
        except Exception as e:
            logger.error("Batch Neo4j relationship creation failed: %s", e)
            return 0

        # Batch PG insert
        for obj in pg_objects:
            self._db.add(obj)
        await self._db.flush()

        logger.info("Batch-created %d relationships", len(pg_objects))
        return len(pg_objects)

    async def get_graph_visualization(
        self,
        document_id: uuid.UUID | None = None,
        entity_types: list[str] | None = None,
        limit: int = 100,
        source: str | None = None,
    ) -> GraphVisualization:
        """Get graph data formatted for visualization.

        Args:
            source: Optional filter — 'upload' or 'google_drive'. Filters
                    entities by the source of their parent document.
        """
        try:
            # Build entity query
            stmt = select(KnowledgeEntity)
            if document_id:
                stmt = stmt.where(KnowledgeEntity.source_document_id == document_id)
            if source:
                from app.domain.documents.models import Document
                stmt = stmt.join(
                    Document,
                    KnowledgeEntity.source_document_id == Document.id,
                ).where(Document.source == source)
            if entity_types:
                stmt = stmt.where(KnowledgeEntity.entity_type.in_(entity_types))
            stmt = stmt.limit(limit)

            result = await self._db.execute(stmt)
            entities = result.scalars().all()

            entity_ids = [e.id for e in entities]

            # Get relationships between these entities
            rel_stmt = select(KnowledgeRelationship).where(
                KnowledgeRelationship.source_entity_id.in_(entity_ids),
                KnowledgeRelationship.target_entity_id.in_(entity_ids),
            )
            rel_result = await self._db.execute(rel_stmt)
            relationships = rel_result.scalars().all()

            # Build visualization data
            nodes = [
                GraphNode(
                    id=str(e.id),
                    label=e.name,
                    type=e.entity_type,
                    description=e.description,
                )
                for e in entities
            ]

            edges = [
                GraphEdge(
                    source=str(r.source_entity_id),
                    target=str(r.target_entity_id),
                    label=r.relationship_type,
                    weight=r.weight,
                )
                for r in relationships
            ]

            # Get total counts
            total_entities_stmt = select(sa_func.count(KnowledgeEntity.id))
            total_rels_stmt = select(sa_func.count(KnowledgeRelationship.id))
            total_entities = (await self._db.execute(total_entities_stmt)).scalar() or 0
            total_rels = (await self._db.execute(total_rels_stmt)).scalar() or 0

            return GraphVisualization(
                nodes=nodes,
                edges=edges,
                total_nodes=total_entities,
                total_edges=total_rels,
            )

        except Exception as e:
            logger.error("Failed to get graph visualization: %s", e)
            raise GraphQueryError(f"Failed to get visualization: {e}") from e

    async def get_entity_neighbors(
        self,
        entity_id: uuid.UUID,
        depth: int = 1,
        limit: int = 50,
    ) -> GraphVisualization:
        """Get neighboring entities and relationships for graph expansion."""
        try:
            entity = await self._db.get(KnowledgeEntity, entity_id)
            if not entity:
                raise EntityNotFoundError(str(entity_id))

            # Find neighbors via Neo4j traversal
            records = await self._neo4j.execute_read(
                """
                MATCH path = (start {neo4j_id: $neo4j_id})-[*1..""" + str(depth) + """]->(neighbor)
                WITH DISTINCT neighbor
                LIMIT $limit
                RETURN collect(neighbor.neo4j_id) AS neighbor_ids
                """,
                {"neo4j_id": entity.neo4j_id, "limit": limit},
            )

            # Collect all neighbor neo4j_ids
            neighbor_neo4j_ids: list[str] = []
            if records:
                neighbor_neo4j_ids = records[0].get("neighbor_ids", [])

            # Also get undirected neighbors
            records2 = await self._neo4j.execute_read(
                """
                MATCH (start {neo4j_id: $neo4j_id})<-[*1..""" + str(depth) + """]-(neighbor)
                WITH DISTINCT neighbor
                LIMIT $limit
                RETURN collect(neighbor.neo4j_id) AS neighbor_ids
                """,
                {"neo4j_id": entity.neo4j_id, "limit": limit},
            )
            if records2:
                neighbor_neo4j_ids.extend(records2[0].get("neighbor_ids", []))

            # Deduplicate
            neighbor_neo4j_ids = list(set(neighbor_neo4j_ids))

            if not neighbor_neo4j_ids:
                return GraphVisualization(
                    nodes=[GraphNode(
                        id=str(entity.id),
                        label=entity.name,
                        type=entity.entity_type,
                        description=entity.description,
                    )],
                    edges=[],
                    total_nodes=1,
                    total_edges=0,
                )

            # Resolve neighbors from PostgreSQL
            stmt = select(KnowledgeEntity).where(
                KnowledgeEntity.neo4j_id.in_(neighbor_neo4j_ids)
            )
            result = await self._db.execute(stmt)
            neighbors = result.scalars().all()

            all_entities = [entity] + list(neighbors)
            all_entity_ids = [e.id for e in all_entities]

            # Get relationships between all these entities
            rel_stmt = select(KnowledgeRelationship).where(
                KnowledgeRelationship.source_entity_id.in_(all_entity_ids),
                KnowledgeRelationship.target_entity_id.in_(all_entity_ids),
            )
            rel_result = await self._db.execute(rel_stmt)
            relationships = rel_result.scalars().all()

            nodes = [
                GraphNode(
                    id=str(e.id),
                    label=e.name,
                    type=e.entity_type,
                    description=e.description,
                )
                for e in all_entities
            ]

            edges = [
                GraphEdge(
                    source=str(r.source_entity_id),
                    target=str(r.target_entity_id),
                    label=r.relationship_type,
                    weight=r.weight,
                )
                for r in relationships
            ]

            return GraphVisualization(
                nodes=nodes,
                edges=edges,
                total_nodes=len(nodes),
                total_edges=len(edges),
            )

        except EntityNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to get entity neighbors: %s", e)
            raise GraphQueryError(f"Failed to get entity neighbors: {e}") from e

    async def get_stats(self) -> KnowledgeStats:
        """Get knowledge graph statistics."""
        # Entity counts by type
        entity_type_stmt = select(
            KnowledgeEntity.entity_type,
            sa_func.count(KnowledgeEntity.id),
        ).group_by(KnowledgeEntity.entity_type)
        entity_types_result = await self._db.execute(entity_type_stmt)
        entity_types = dict(entity_types_result.all())

        # Relationship counts by type
        rel_type_stmt = select(
            KnowledgeRelationship.relationship_type,
            sa_func.count(KnowledgeRelationship.id),
        ).group_by(KnowledgeRelationship.relationship_type)
        rel_types_result = await self._db.execute(rel_type_stmt)
        relationship_types = dict(rel_types_result.all())

        total_entities = sum(entity_types.values())
        total_relationships = sum(relationship_types.values())

        # Count embeddings from the document_embeddings table
        from app.domain.knowledge.models import DocumentEmbedding
        embedding_count_stmt = select(sa_func.count(DocumentEmbedding.id))
        total_embeddings = (await self._db.execute(embedding_count_stmt)).scalar() or 0

        return KnowledgeStats(
            total_entities=total_entities,
            total_relationships=total_relationships,
            total_embeddings=total_embeddings,
            entity_types=entity_types,
            relationship_types=relationship_types,
        )

    async def delete_document_entities(self, document_id: uuid.UUID) -> int:
        """Delete all entities and relationships for a document."""
        try:
            # Get entities for this document
            stmt = select(KnowledgeEntity).where(
                KnowledgeEntity.source_document_id == document_id
            )
            result = await self._db.execute(stmt)
            entities = result.scalars().all()

            if not entities:
                return 0

            # Delete from Neo4j
            neo4j_ids = [e.neo4j_id for e in entities]
            await self._neo4j.execute_write(
                """
                UNWIND $ids AS neo_id
                MATCH (n {neo4j_id: neo_id})
                DETACH DELETE n
                """,
                {"ids": neo4j_ids},
            )

            # Delete from PostgreSQL (cascade handles relationships)
            count = len(entities)
            for entity in entities:
                await self._db.delete(entity)
            await self._db.flush()

            logger.info("Deleted %d entities for document %s", count, document_id)
            return count

        except Exception as e:
            logger.error("Failed to delete document entities: %s", e)
            raise GraphBuildError(f"Failed to delete entities: {e}") from e

    async def _get_entity_relationships(
        self, neo4j_id: str
    ) -> list[RelationshipResponse]:
        """Get all relationships for an entity from Neo4j.

        Resolves real PostgreSQL entity/relationship IDs by looking up
        neo4j_ids instead of using placeholder UUIDs.
        """
        records = await self._neo4j.execute_read(
            """
            MATCH (n {neo4j_id: $id})-[r]-(m)
            RETURN type(r) AS rel_type, r.neo4j_id AS rel_id, r.weight AS weight,
                   m.neo4j_id AS other_id, m.name AS other_name, m.entity_type AS other_type,
                   startNode(r).neo4j_id AS source_neo4j_id,
                   n.neo4j_id AS self_neo4j_id
            """,
            {"id": neo4j_id},
        )

        if not records:
            return []

        # Collect all neo4j_ids we need to resolve
        all_neo4j_ids = set()
        all_rel_neo4j_ids = set()
        for record in records:
            all_neo4j_ids.add(record.get("self_neo4j_id", ""))
            all_neo4j_ids.add(record.get("other_id", ""))
            if record.get("rel_id"):
                all_rel_neo4j_ids.add(record["rel_id"])

        all_neo4j_ids.discard("")

        # Batch resolve entity IDs from PostgreSQL
        entity_map: dict[str, tuple[uuid.UUID, str]] = {}  # neo4j_id -> (pg_id, name)
        if all_neo4j_ids:
            stmt = select(
                KnowledgeEntity.neo4j_id,
                KnowledgeEntity.id,
                KnowledgeEntity.name,
            ).where(KnowledgeEntity.neo4j_id.in_(list(all_neo4j_ids)))
            result = await self._db.execute(stmt)
            for neo_id, pg_id, name in result.all():
                entity_map[neo_id] = (pg_id, name)

        # Batch resolve relationship IDs
        rel_id_map: dict[str, uuid.UUID] = {}  # neo4j_id -> pg_id
        if all_rel_neo4j_ids:
            rel_stmt = select(
                KnowledgeRelationship.neo4j_id,
                KnowledgeRelationship.id,
            ).where(KnowledgeRelationship.neo4j_id.in_(list(all_rel_neo4j_ids)))
            rel_result = await self._db.execute(rel_stmt)
            for neo_id, pg_id in rel_result.all():
                rel_id_map[neo_id] = pg_id

        relationships = []
        for record in records:
            source_neo = record.get("source_neo4j_id", "")
            other_neo = record.get("other_id", "")
            rel_neo = record.get("rel_id", "")

            # Determine source/target based on relationship direction
            source_info = entity_map.get(source_neo)
            target_neo = other_neo if source_neo == neo4j_id else neo4j_id
            target_info = entity_map.get(other_neo)

            # If this entity is the source
            if source_neo == neo4j_id:
                src_id, src_name = entity_map.get(neo4j_id, (uuid.UUID(int=0), ""))
                tgt_id, tgt_name = entity_map.get(other_neo, (uuid.UUID(int=0), record.get("other_name", "")))
            else:
                src_id, src_name = entity_map.get(other_neo, (uuid.UUID(int=0), record.get("other_name", "")))
                tgt_id, tgt_name = entity_map.get(neo4j_id, (uuid.UUID(int=0), ""))

            relationships.append(
                RelationshipResponse(
                    id=rel_id_map.get(rel_neo, uuid.UUID(int=0)),
                    neo4j_id=rel_neo,
                    relationship_type=record["rel_type"],
                    source_entity_id=src_id,
                    target_entity_id=tgt_id,
                    source_entity_name=src_name,
                    target_entity_name=tgt_name,
                    weight=record.get("weight", 1.0),
                    created_at=__import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ),
                )
            )

        return relationships


def _sanitize_label(label: str) -> str:
    """Sanitize a Neo4j label to prevent injection.

    Only allows alphanumeric characters and underscores.
    """
    return "".join(c for c in label if c.isalnum() or c == "_")
