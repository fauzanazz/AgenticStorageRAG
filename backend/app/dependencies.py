"""Dependency injection container.

All external service dependencies are provided through FastAPI's
dependency injection system. This keeps domain code decoupled from
infrastructure concerns.
"""

from app.config import Settings, get_settings


async def get_current_settings() -> Settings:
    """Provide application settings as a dependency."""
    return get_settings()


# TODO: Add database session dependency
# async def get_db_session() -> AsyncGenerator[AsyncSession, None]: ...

# TODO: Add Neo4j session dependency
# async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]: ...

# TODO: Add Redis client dependency
# async def get_redis() -> Redis: ...

# TODO: Add current user dependency (after auth domain)
# async def get_current_user() -> User: ...
