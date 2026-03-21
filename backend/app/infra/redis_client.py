"""Redis client wrapper.

Provides connection management and cache operations.

Background job dispatch is handled by Celery (see app/celery_app.py).
This client is used only for caching (get/set/delete/get_json/set_json).
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client with connection pooling and cache support.

    Initialized once during app startup, shared via dependency injection.
    Background job dispatch is handled by Celery, not this client.
    """

    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None  # type: ignore[type-arg]

    async def connect(self) -> None:
        """Initialize Redis connection pool."""
        settings = get_settings()
        self._client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
        # Verify connectivity
        await self._client.ping()
        logger.info("Redis connected: %s", settings.redis_url)

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    @property
    def client(self) -> aioredis.Redis:  # type: ignore[type-arg]
        """Get the Redis client, raising if not connected."""
        if self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    async def health_check(self) -> dict[str, str]:
        """Check Redis connectivity."""
        try:
            pong = await self.client.ping()
            return {"status": "healthy" if pong else "unhealthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    # --- Cache operations ---

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ttl: timedelta | int | None = None,
    ) -> None:
        """Set a value with optional TTL."""
        if ttl is not None:
            await self.client.set(key, value, ex=ttl)
        else:
            await self.client.set(key, value)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        await self.client.delete(key)

    async def get_json(self, key: str) -> Any | None:
        """Get and deserialize a JSON value."""
        raw = await self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: timedelta | int | None = None,
    ) -> None:
        """Serialize and set a JSON value."""
        await self.set(key, json.dumps(value, default=str), ttl=ttl)


# Module-level singleton (initialized via lifespan)
redis_client = RedisClient()
