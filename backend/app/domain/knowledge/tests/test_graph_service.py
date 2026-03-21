"""Tests for knowledge graph service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.knowledge.exceptions import (
    EntityNotFoundError,
    GraphBuildError,
)
from app.domain.knowledge.graph_service import GraphService, _sanitize_label
from app.domain.knowledge.models import KnowledgeEntity, KnowledgeRelationship
from app.domain.knowledge.schemas import (
    EntityCreate,
    RelationshipCreate,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_neo4j() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_db: AsyncMock, mock_neo4j: AsyncMock) -> GraphService:
    return GraphService(db=mock_db, neo4j=mock_neo4j)


class TestSanitizeLabel:
    """Tests for label sanitization."""

    def test_clean_label(self) -> None:
        assert _sanitize_label("Person") == "Person"

    def test_label_with_spaces(self) -> None:
        assert _sanitize_label("Some Label") == "SomeLabel"

    def test_label_with_special_chars(self) -> None:
        assert _sanitize_label("Entity-Type!") == "EntityType"

    def test_label_with_underscores(self) -> None:
        assert _sanitize_label("RELATED_TO") == "RELATED_TO"


class TestCreateEntity:
    """Tests for entity creation."""

    @pytest.mark.asyncio
    async def test_create_entity_success(
        self, service: GraphService, mock_db: AsyncMock, mock_neo4j: AsyncMock
    ) -> None:
        entity_create = EntityCreate(
            entity_type="Person",
            name="John Doe",
            description="A test entity",
        )

        now = datetime.now(UTC)

        def set_entity_defaults(entity: KnowledgeEntity) -> None:
            entity.id = uuid.uuid4()
            entity.created_at = now
            entity.updated_at = now

        mock_db.add.side_effect = set_entity_defaults
        mock_neo4j.execute_write.return_value = []

        result = await service.create_entity(entity_create)

        assert result.name == "John Doe"
        assert result.entity_type == "Person"
        assert result.description == "A test entity"
        mock_neo4j.execute_write.assert_called_once()
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_entity_with_properties(
        self, service: GraphService, mock_db: AsyncMock, mock_neo4j: AsyncMock
    ) -> None:
        entity_create = EntityCreate(
            entity_type="Organization",
            name="Acme Corp",
            properties={"founded": "1990", "industry": "Tech"},
        )

        now = datetime.now(UTC)

        def set_defaults(entity: KnowledgeEntity) -> None:
            entity.id = uuid.uuid4()
            entity.created_at = now
            entity.updated_at = now

        mock_db.add.side_effect = set_defaults
        mock_neo4j.execute_write.return_value = []

        result = await service.create_entity(entity_create)
        assert result.name == "Acme Corp"
        assert result.properties == {"founded": "1990", "industry": "Tech"}

    @pytest.mark.asyncio
    async def test_create_entity_neo4j_failure(
        self, service: GraphService, mock_neo4j: AsyncMock
    ) -> None:
        mock_neo4j.execute_write.side_effect = Exception("Connection refused")

        with pytest.raises(GraphBuildError, match="Failed to create entity"):
            await service.create_entity(EntityCreate(entity_type="Person", name="Test"))


class TestGetEntity:
    """Tests for entity retrieval."""

    @pytest.mark.asyncio
    async def test_get_entity_not_found(self, service: GraphService, mock_db: AsyncMock) -> None:
        entity_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(EntityNotFoundError):
            await service.get_entity(entity_id)

    @pytest.mark.asyncio
    async def test_get_entity_success(
        self, service: GraphService, mock_db: AsyncMock, mock_neo4j: AsyncMock
    ) -> None:
        entity_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_entity = MagicMock(spec=KnowledgeEntity)
        mock_entity.id = entity_id
        mock_entity.neo4j_id = "neo4j-123"
        mock_entity.entity_type = "Person"
        mock_entity.name = "Jane Doe"
        mock_entity.description = "Test"
        mock_entity.properties_json = None
        mock_entity.source_document_id = None
        mock_entity.created_at = now
        mock_entity.updated_at = now

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity
        mock_db.execute.return_value = mock_result

        mock_neo4j.execute_read.return_value = []

        result = await service.get_entity(entity_id)
        assert result.name == "Jane Doe"
        assert result.entity_type == "Person"


class TestCreateRelationship:
    """Tests for relationship creation."""

    @pytest.mark.asyncio
    async def test_source_not_found(self, service: GraphService, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None

        with pytest.raises(EntityNotFoundError):
            await service.create_relationship(
                RelationshipCreate(
                    source_entity_id=uuid.uuid4(),
                    target_entity_id=uuid.uuid4(),
                    relationship_type="RELATED_TO",
                )
            )

    @pytest.mark.asyncio
    async def test_create_relationship_success(
        self, service: GraphService, mock_db: AsyncMock, mock_neo4j: AsyncMock
    ) -> None:
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        now = datetime.now(UTC)

        source = MagicMock(spec=KnowledgeEntity)
        source.neo4j_id = "src-neo4j"
        source.name = "Source"

        target = MagicMock(spec=KnowledgeEntity)
        target.neo4j_id = "tgt-neo4j"
        target.name = "Target"

        async def mock_get(model: type, entity_id: uuid.UUID) -> MagicMock | None:
            if entity_id == source_id:
                return source
            if entity_id == target_id:
                return target
            return None

        mock_db.get = mock_get
        mock_neo4j.execute_write.return_value = []

        def set_rel_defaults(rel: KnowledgeRelationship) -> None:
            rel.id = uuid.uuid4()
            rel.created_at = now

        mock_db.add.side_effect = set_rel_defaults

        result = await service.create_relationship(
            RelationshipCreate(
                source_entity_id=source_id,
                target_entity_id=target_id,
                relationship_type="WORKS_AT",
                weight=0.9,
            )
        )

        assert result.relationship_type == "WORKS_AT"
        assert result.source_entity_name == "Source"
        assert result.target_entity_name == "Target"
        assert result.weight == 0.9


class TestGetGraphVisualization:
    """Tests for graph visualization."""

    @pytest.mark.asyncio
    async def test_empty_graph(self, service: GraphService, mock_db: AsyncMock) -> None:
        # Mock entities query
        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = []

        # Mock relationships query
        rels_result = MagicMock()
        rels_result.scalars.return_value.all.return_value = []

        # Mock count queries
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_db.execute.side_effect = [
            entities_result,
            rels_result,
            count_result,
            count_result,
        ]

        result = await service.get_graph_visualization()
        assert result.nodes == []
        assert result.edges == []


class TestGetStats:
    """Tests for knowledge graph statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, service: GraphService, mock_db: AsyncMock) -> None:
        entity_types_result = MagicMock()
        entity_types_result.all.return_value = [("Person", 5), ("Organization", 3)]

        rel_types_result = MagicMock()
        rel_types_result.all.return_value = [("WORKS_AT", 4), ("KNOWS", 2)]

        embedding_count_result = MagicMock()
        embedding_count_result.scalar.return_value = 42

        mock_db.execute.side_effect = [
            entity_types_result,
            rel_types_result,
            embedding_count_result,
        ]

        result = await service.get_stats()
        assert result.total_entities == 8
        assert result.total_relationships == 6
        assert result.total_embeddings == 42
        assert result.entity_types == {"Person": 5, "Organization": 3}
        assert result.relationship_types == {"WORKS_AT": 4, "KNOWS": 2}


class TestDeleteDocumentEntities:
    """Tests for deleting document entities."""

    @pytest.mark.asyncio
    async def test_delete_no_entities(self, service: GraphService, mock_db: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        count = await service.delete_document_entities(uuid.uuid4())
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_entities_success(
        self, service: GraphService, mock_db: AsyncMock, mock_neo4j: AsyncMock
    ) -> None:
        entity1 = MagicMock(spec=KnowledgeEntity)
        entity1.neo4j_id = "neo4j-1"
        entity2 = MagicMock(spec=KnowledgeEntity)
        entity2.neo4j_id = "neo4j-2"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity1, entity2]
        mock_db.execute.return_value = mock_result

        mock_neo4j.execute_write.return_value = []

        count = await service.delete_document_entities(uuid.uuid4())
        assert count == 2
        mock_neo4j.execute_write.assert_called_once()
