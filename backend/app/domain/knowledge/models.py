"""Knowledge domain models.

SQLAlchemy models for storing document embeddings (pgvector)
and Neo4j entity/relationship metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database import Base


class DocumentEmbedding(Base):
    """Stores vector embeddings for document chunks.

    Each chunk from a processed document gets an embedding vector
    stored in pgvector for similarity search.
    """

    __tablename__ = "document_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Store embedding as float array; pgvector extension handles similarity ops
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)
    embedding_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="text-embedding-3-small"
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_embeddings_document_id", "document_id"),
        Index("idx_embeddings_chunk_id", "chunk_id"),
    )


class KnowledgeEntity(Base):
    """Metadata record for entities stored in Neo4j.

    This is a PostgreSQL shadow record that tracks which entities
    exist in the knowledge graph, enabling SQL-based queries
    and joins with document data.
    """

    __tablename__ = "knowledge_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    neo4j_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    relationships_from: Mapped[list[KnowledgeRelationship]] = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )
    relationships_to: Mapped[list[KnowledgeRelationship]] = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.target_entity_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_entity_type", "entity_type"),
        Index("idx_entity_name", "name"),
        Index("idx_entity_source", "source_document_id"),
    )


class KnowledgeRelationship(Base):
    """Metadata record for relationships stored in Neo4j.

    Mirrors the Neo4j relationship for SQL-side querying.
    """

    __tablename__ = "knowledge_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    neo4j_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    properties_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_entity: Mapped[KnowledgeEntity] = relationship(
        "KnowledgeEntity",
        foreign_keys=[source_entity_id],
        back_populates="relationships_from",
    )
    target_entity: Mapped[KnowledgeEntity] = relationship(
        "KnowledgeEntity",
        foreign_keys=[target_entity_id],
        back_populates="relationships_to",
    )

    __table_args__ = (
        Index("idx_rel_type", "relationship_type"),
        Index("idx_rel_source", "source_entity_id"),
        Index("idx_rel_target", "target_entity_id"),
        Index("idx_rel_document", "source_document_id"),
    )
