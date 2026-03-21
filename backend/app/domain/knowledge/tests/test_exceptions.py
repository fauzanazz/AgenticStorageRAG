"""Tests for knowledge exceptions."""

from __future__ import annotations

from app.domain.knowledge.exceptions import (
    DuplicateEntityError,
    EmbeddingError,
    EntityNotFoundError,
    GraphBuildError,
    GraphQueryError,
    KnowledgeBaseError,
    RelationshipNotFoundError,
)


class TestExceptions:
    """Tests for knowledge domain exceptions."""

    def test_base_error(self) -> None:
        err = KnowledgeBaseError()
        assert str(err) == "Knowledge domain error"

    def test_entity_not_found(self) -> None:
        err = EntityNotFoundError("abc-123")
        assert "abc-123" in str(err)
        assert err.entity_id == "abc-123"

    def test_relationship_not_found(self) -> None:
        err = RelationshipNotFoundError("rel-456")
        assert "rel-456" in str(err)
        assert err.relationship_id == "rel-456"

    def test_embedding_error(self) -> None:
        err = EmbeddingError("custom message")
        assert str(err) == "custom message"

    def test_graph_build_error(self) -> None:
        err = GraphBuildError()
        assert "Failed to build" in str(err)

    def test_graph_query_error(self) -> None:
        err = GraphQueryError()
        assert "Failed to query" in str(err)

    def test_duplicate_entity_error(self) -> None:
        err = DuplicateEntityError("John", "Person")
        assert "John" in str(err)
        assert "Person" in str(err)
        assert err.name == "John"
        assert err.entity_type == "Person"
