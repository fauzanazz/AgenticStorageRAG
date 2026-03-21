"""Knowledge domain exceptions."""


class KnowledgeBaseError(Exception):
    """Base exception for the knowledge domain."""

    def __init__(self, message: str = "Knowledge domain error"):
        self.message = message
        super().__init__(self.message)


class EntityNotFoundError(KnowledgeBaseError):
    """Raised when a knowledge entity is not found."""

    def __init__(self, entity_id: str):
        super().__init__(f"Entity not found: {entity_id}")
        self.entity_id = entity_id


class RelationshipNotFoundError(KnowledgeBaseError):
    """Raised when a knowledge relationship is not found."""

    def __init__(self, relationship_id: str):
        super().__init__(f"Relationship not found: {relationship_id}")
        self.relationship_id = relationship_id


class EmbeddingError(KnowledgeBaseError):
    """Raised when embedding generation fails."""

    def __init__(self, message: str = "Failed to generate embedding"):
        super().__init__(message)


class GraphBuildError(KnowledgeBaseError):
    """Raised when knowledge graph construction fails."""

    def __init__(self, message: str = "Failed to build knowledge graph"):
        super().__init__(message)


class GraphQueryError(KnowledgeBaseError):
    """Raised when a graph query fails."""

    def __init__(self, message: str = "Failed to query knowledge graph"):
        super().__init__(message)


class DuplicateEntityError(KnowledgeBaseError):
    """Raised when attempting to create a duplicate entity."""

    def __init__(self, name: str, entity_type: str):
        super().__init__(f"Entity '{name}' of type '{entity_type}' already exists")
        self.name = name
        self.entity_type = entity_type
