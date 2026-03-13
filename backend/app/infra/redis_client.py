"""Redis client wrapper.

Provides connection management, health check, and queue abstractions
for caching and background job dispatch.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from datetime import timedelta

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client with connection pooling and job queue support.

    Initialized once during app startup, shared via dependency injection.
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

    # --- Queue operations (for background jobs) ---

    async def enqueue(self, queue_name: str, job_data: dict[str, Any]) -> None:
        """Push a job onto a Redis list (queue).

        Args:
            queue_name: Name of the queue (e.g., "jobs:documents", "jobs:ingestion")
            job_data: Job payload as a dictionary
        """
        await self.client.rpush(queue_name, json.dumps(job_data, default=str))
        logger.debug("Job enqueued to %s: %s", queue_name, job_data.get("type", "unknown"))

    async def dequeue(self, queue_name: str, timeout: int = 0) -> dict[str, Any] | None:
        """Pop a job from a Redis list (blocking).

        Args:
            queue_name: Name of the queue
            timeout: Blocking timeout in seconds (0 = block forever)

        Returns:
            Job payload dict, or None if timeout reached
        """
        result = await self.client.blpop(queue_name, timeout=timeout)
        if result is None:
            return None
        _, raw = result
        return json.loads(raw)

    async def queue_length(self, queue_name: str) -> int:
        """Get the number of jobs in a queue."""
        return await self.client.llen(queue_name)


# Module-level singleton (initialized via lifespan)
redis_client = RedisClient()
