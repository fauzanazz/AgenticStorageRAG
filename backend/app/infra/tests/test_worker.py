"""Tests for background job worker."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infra.worker import (
    HANDLERS,
    register_handler,
    process_job,
    MAX_RETRIES,
)


class TestRegisterHandler:
    """Tests for job handler registration."""

    def test_register_handler(self) -> None:
        """register_handler should add handler to HANDLERS dict."""
        # Clean up after test
        original = dict(HANDLERS)

        async def dummy_handler(data: dict) -> None:
            pass

        register_handler("test_job_type", dummy_handler)

        assert "test_job_type" in HANDLERS
        assert HANDLERS["test_job_type"] is dummy_handler

        # Restore
        HANDLERS.clear()
        HANDLERS.update(original)


class TestProcessJob:
    """Tests for job processing with retry and DLQ."""

    @pytest.mark.asyncio
    async def test_process_job_dispatches_to_handler(self) -> None:
        """process_job should call the registered handler."""
        original = dict(HANDLERS)

        mock_handler = AsyncMock()
        HANDLERS["test_process"] = mock_handler

        job_data = {"type": "test_process", "id": "job-1", "payload": "test"}
        await process_job(job_data, "jobs:test")

        mock_handler.assert_called_once_with(job_data)

        HANDLERS.clear()
        HANDLERS.update(original)

    @pytest.mark.asyncio
    async def test_process_job_handles_missing_type(self) -> None:
        """process_job should log error for jobs without type."""
        # Should not raise, just log
        await process_job({"data": "no type field"}, "jobs:test")

    @pytest.mark.asyncio
    @patch("app.infra.worker.redis_client")
    async def test_process_job_handles_unknown_type(self, mock_redis: MagicMock) -> None:
        """process_job should move unhandled job types to DLQ."""
        mock_redis.move_to_dlq = AsyncMock()

        job_data = {"type": "unknown_type_xyz"}
        await process_job(job_data, "jobs:test")

        # Should be moved to DLQ
        mock_redis.move_to_dlq.assert_called_once()
        call_args = mock_redis.move_to_dlq.call_args
        assert call_args[0][0] == "jobs:test"
        assert "_dlq_reason" in call_args[0][1]

    @pytest.mark.asyncio
    @patch("app.infra.worker.redis_client")
    async def test_process_job_retries_on_failure(self, mock_redis: MagicMock) -> None:
        """process_job should re-enqueue with backoff on first failure."""
        original = dict(HANDLERS)

        mock_redis.enqueue = AsyncMock()

        async def failing_handler(data: dict) -> None:
            raise ValueError("Handler exploded")

        HANDLERS["failing_job"] = failing_handler

        job_data = {"type": "failing_job", "id": "fail-1", "_retry_count": 0}
        await process_job(job_data, "jobs:test")

        # Should be re-enqueued with incremented retry count
        mock_redis.enqueue.assert_called_once()
        call_args = mock_redis.enqueue.call_args
        assert call_args[0][0] == "jobs:test"
        assert call_args[0][1]["_retry_count"] == 1

        HANDLERS.clear()
        HANDLERS.update(original)

    @pytest.mark.asyncio
    @patch("app.infra.worker.redis_client")
    async def test_process_job_moves_to_dlq_after_max_retries(self, mock_redis: MagicMock) -> None:
        """process_job should move to DLQ after max retries exceeded."""
        original = dict(HANDLERS)

        mock_redis.move_to_dlq = AsyncMock()

        async def failing_handler(data: dict) -> None:
            raise ValueError("Handler exploded")

        HANDLERS["failing_job"] = failing_handler

        job_data = {"type": "failing_job", "id": "fail-1", "_retry_count": MAX_RETRIES}
        await process_job(job_data, "jobs:test")

        # Should be moved to DLQ
        mock_redis.move_to_dlq.assert_called_once()
        call_args = mock_redis.move_to_dlq.call_args
        assert call_args[0][0] == "jobs:test"
        assert "_dlq_reason" in call_args[0][1]

        HANDLERS.clear()
        HANDLERS.update(original)
