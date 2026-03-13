"""Dependency injection container.

All external service dependencies are provided through FastAPI's
dependency injection system. This keeps domain code decoupled from
infrastructure concerns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.infra.database import get_db_session
from app.infra.neo4j_client import Neo4jClient, neo4j_client
from app.infra.redis_client import RedisClient, redis_client
from app.infra.storage import StorageClient, storage_client
from app.infra.llm import LLMProvider, llm_provider


async def get_current_settings() -> Settings:
    """Provide application settings as a dependency."""
    return get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session as a dependency.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async for session in get_db_session():
        yield session


async def get_neo4j() -> Neo4jClient:
    """Provide the Neo4j client as a dependency.

    Usage:
        @router.get("/graph")
        async def get_graph(neo4j: Neo4jClient = Depends(get_neo4j)):
            ...
    """
    return neo4j_client


async def get_redis() -> RedisClient:
    """Provide the Redis client as a dependency.

    Usage:
        @router.get("/cached")
        async def get_cached(redis: RedisClient = Depends(get_redis)):
            ...
    """
    return redis_client


async def get_storage() -> StorageClient:
    """Provide the Supabase Storage client as a dependency.

    Usage:
        @router.post("/upload")
        async def upload(storage: StorageClient = Depends(get_storage)):
            ...
    """
    return storage_client


async def get_llm() -> LLMProvider:
    """Provide the LLM provider as a dependency.

    Usage:
        @router.post("/chat")
        async def chat(llm: LLMProvider = Depends(get_llm)):
            ...
    """
    return llm_provider


# TODO: Add current user dependency (after auth domain)
# async def get_current_user(
#     db: AsyncSession = Depends(get_db),
#     token: str = Depends(oauth2_scheme),
# ) -> User:
#     ...
