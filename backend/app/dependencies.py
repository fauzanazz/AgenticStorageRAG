"""Dependency injection container.

All external service dependencies are provided through FastAPI's
dependency injection system. This keeps domain code decoupled from
infrastructure concerns.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.infra.database import get_db_session
from app.infra.neo4j_client import Neo4jClient, neo4j_client
from app.infra.redis_client import RedisClient, redis_client
from app.infra.storage import StorageClient, storage_client
from app.infra.llm import LLMProvider, llm_provider
from app.domain.settings.models import UserModelSettings

# OAuth2 scheme for token extraction from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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
    """Provide the Neo4j client as a dependency."""
    return neo4j_client


async def get_redis() -> RedisClient:
    """Provide the Redis client as a dependency."""
    return redis_client


async def get_storage() -> StorageClient:
    """Provide the Supabase Storage client as a dependency."""
    return storage_client


async def get_llm() -> LLMProvider:
    """Provide the LLM provider as a dependency."""
    return llm_provider


async def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> uuid.UUID:
    """Extract and validate the current user ID from the JWT access token.

    Usage:
        @router.get("/protected")
        async def protected(user_id: uuid.UUID = Depends(get_current_user_id)):
            ...
    """
    from app.domain.auth.token import TokenService
    from app.domain.auth.exceptions import InvalidTokenError

    token_service = TokenService()
    try:
        payload = token_service.verify_token(token)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not an access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return uuid.UUID(payload["sub"])


async def get_current_user(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> "User":
    """Get the full current user object from the database.

    Usage:
        @router.get("/protected")
        async def protected(user: User = Depends(get_current_user)):
            ...
    """
    from app.domain.auth.models import User

    result = await db.get(User, user_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return result


async def get_user_model_settings(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserModelSettings | None:
    """Load the current user's raw model settings row (with encrypted keys).

    Returns None if the user has no settings configured yet.
    Falls back gracefully — services must handle None and use server defaults.
    """
    from app.domain.settings.service import SettingsService

    service = SettingsService(db=db)
    return await service.get_raw_settings(user_id)
