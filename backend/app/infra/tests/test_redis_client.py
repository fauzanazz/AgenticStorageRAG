"""Tests for Redis client wrapper."""

import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import timedelta

import pytest

from app.infra.redis_client import RedisClient


class TestRedisClientInit:
    """Tests for Redis client initialization."""

    def test_initial_state(self) -> None:
        """Client should start with no connection."""
        client = RedisClient()
        assert client._client is None

    def test_client_property_raises_when_not_connected(self) -> None:
        """Accessing client before connect should raise RuntimeError."""
        client = RedisClient()
        with pytest.raises(RuntimeError, match="Redis not connected"):
            _ = client.client


class TestRedisClientConnect:
    """Tests for Redis connection."""

    @pytest.mark.asyncio
    @patch("app.infra.redis_client.get_settings")
    @patch("app.infra.redis_client.aioredis")
    async def test_connect_initializes_client(
        self,
        mock_aioredis: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """connect() should create client and verify with ping."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_get_settings.return_value = mock_settings

        mock_redis = AsyncMock()
        mock_aioredis.from_url.return_value = mock_redis

        client = RedisClient()
        await client.connect()

        mock_aioredis.from_url.assert_called_once_with(
            "redis://localhost:6379/0",
            decode_responses=True,
            max_connections=20,
        )
        mock_redis.ping.assert_called_once()
        assert client._client is mock_redis


class TestRedisClientClose:
    """Tests for Redis disconnection."""

    @pytest.mark.asyncio
    async def test_close_releases_client(self) -> None:
        """close() should close and nullify the client."""
        client = RedisClient()
        mock_redis = AsyncMock()
        client._client = mock_redis

        await client.close()

        mock_redis.close.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_noop_when_not_connected(self) -> None:
        """close() should be safe when client is None."""
        client = RedisClient()
        await client.close()  # Should not raise


class TestRedisClientCache:
    """Tests for cache operations."""

    @pytest.mark.asyncio
    async def test_get(self) -> None:
        """get() should delegate to Redis GET."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "test_value"
        client._client = mock_redis

        result = await client.get("test_key")

        assert result == "test_value"
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_set_without_ttl(self) -> None:
        """set() without TTL should call SET without expiry."""
        client = RedisClient()
        mock_redis = AsyncMock()
        client._client = mock_redis

        await client.set("key", "value")

        mock_redis.set.assert_called_once_with("key", "value")

    @pytest.mark.asyncio
    async def test_set_with_ttl(self) -> None:
        """set() with TTL should call SET with expiry."""
        client = RedisClient()
        mock_redis = AsyncMock()
        client._client = mock_redis

        ttl = timedelta(hours=1)
        await client.set("key", "value", ttl=ttl)

        mock_redis.set.assert_called_once_with("key", "value", ex=ttl)

    @pytest.mark.asyncio
    async def test_get_json(self) -> None:
        """get_json() should deserialize JSON."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"foo": "bar"}'
        client._client = mock_redis

        result = await client.get_json("key")

        assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_get_json_returns_none_for_missing_key(self) -> None:
        """get_json() should return None if key doesn't exist."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        client._client = mock_redis

        result = await client.get_json("missing_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_json(self) -> None:
        """set_json() should serialize and store as JSON."""
        client = RedisClient()
        mock_redis = AsyncMock()
        client._client = mock_redis

        await client.set_json("key", {"foo": "bar"})

        call_args = mock_redis.set.call_args
        stored_value = json.loads(call_args[0][1])
        assert stored_value == {"foo": "bar"}


class TestRedisClientHealthCheck:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_healthy(self) -> None:
        """Should return healthy when ping succeeds."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        client._client = mock_redis

        result = await client.health_check()

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_unhealthy_on_error(self) -> None:
        """Should return unhealthy when ping raises."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Connection refused")
        client._client = mock_redis

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "error" in result
