"""Tests for Redis-backed rate limiter."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastapi import HTTPException

from app.infra.rate_limiter import RateLimit, _get_client_ip, check_rate_limit


def _make_request(client_host: str = "127.0.0.1", forwarded_for: str | None = None) -> MagicMock:
    """Create a mock FastAPI Request with optional X-Forwarded-For."""
    request = MagicMock()
    request.client.host = client_host
    if forwarded_for:
        request.headers.get.return_value = forwarded_for
    else:
        request.headers.get.return_value = None
    return request


class TestGetClientIp:
    """Tests for IP extraction."""

    def test_returns_client_host(self) -> None:
        request = _make_request(client_host="10.0.0.1")
        assert _get_client_ip(request) == "10.0.0.1"

    def test_prefers_x_forwarded_for(self) -> None:
        request = _make_request(client_host="10.0.0.1", forwarded_for="203.0.113.5, 10.0.0.1")
        assert _get_client_ip(request) == "203.0.113.5"

    def test_returns_unknown_when_no_client(self) -> None:
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None
        assert _get_client_ip(request) == "unknown"


SMALL_LIMIT = RateLimit(max_requests=5, window_seconds=60)


class TestCheckRateLimit:
    """Tests for rate limit enforcement."""

    @pytest.mark.asyncio
    @patch("app.infra.rate_limiter.redis_client")
    async def test_allows_requests_under_limit(self, mock_redis_mod: MagicMock) -> None:
        """Requests under the limit should pass through."""
        mock_pipe = AsyncMock()
        # zcard returns count below limit
        mock_pipe.execute.return_value = [None, 4, None, None]
        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        type(mock_redis_mod).client = PropertyMock(return_value=mock_client)

        request = _make_request()
        # Should not raise
        await check_rate_limit(request, SMALL_LIMIT, "rl:test")

    @pytest.mark.asyncio
    @patch("app.infra.rate_limiter.redis_client")
    async def test_blocks_after_limit_exceeded(self, mock_redis_mod: MagicMock) -> None:
        """Requests at or above the limit should get 429."""
        mock_pipe = AsyncMock()
        # zcard returns count at limit
        mock_pipe.execute.return_value = [None, 5, None, None]
        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        type(mock_redis_mod).client = PropertyMock(return_value=mock_client)

        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, SMALL_LIMIT, "rl:test")
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    @patch("app.infra.rate_limiter.redis_client")
    async def test_returns_retry_after_header(self, mock_redis_mod: MagicMock) -> None:
        """429 response should include Retry-After header."""
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 5, None, None]
        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        type(mock_redis_mod).client = PropertyMock(return_value=mock_client)

        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, SMALL_LIMIT, "rl:test")
        assert exc_info.value.headers["Retry-After"] == "60"

    @pytest.mark.asyncio
    @patch("app.infra.rate_limiter.redis_client")
    async def test_fails_open_when_redis_unavailable(self, mock_redis_mod: MagicMock) -> None:
        """If Redis errors, the request should be allowed through."""
        mock_client = MagicMock()
        mock_client.pipeline.side_effect = Exception("Connection refused")
        type(mock_redis_mod).client = PropertyMock(return_value=mock_client)

        request = _make_request()
        # Should not raise
        await check_rate_limit(request, SMALL_LIMIT, "rl:test")

    @pytest.mark.asyncio
    @patch("app.infra.rate_limiter.redis_client")
    async def test_different_ips_have_separate_limits(self, mock_redis_mod: MagicMock) -> None:
        """Two different IPs should get independent rate limit windows."""
        call_keys: list[str] = []

        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 0, None, None]

        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        type(mock_redis_mod).client = PropertyMock(return_value=mock_client)

        # Capture the redis keys used via zadd calls
        original_zadd = mock_pipe.zadd

        def capture_zadd(key: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            call_keys.append(key)
            return original_zadd(key, *args, **kwargs)

        mock_pipe.zadd = capture_zadd

        # Actually, the key is passed to zremrangebyscore first. Let's capture there.
        call_keys.clear()
        original_zrem = mock_pipe.zremrangebyscore

        def capture_zrem(key: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            call_keys.append(key)
            return original_zrem(key, *args, **kwargs)

        mock_pipe.zremrangebyscore = capture_zrem

        req1 = _make_request(client_host="10.0.0.1")
        req2 = _make_request(client_host="10.0.0.2")

        await check_rate_limit(req1, SMALL_LIMIT, "rl:test")
        await check_rate_limit(req2, SMALL_LIMIT, "rl:test")

        assert "rl:test:10.0.0.1" in call_keys
        assert "rl:test:10.0.0.2" in call_keys
