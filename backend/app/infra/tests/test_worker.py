"""Tests for background job worker."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infra.worker import (
    HANDLERS,
    register_handler,
    process_job,
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
    """Tests for job processing."""

    @pytest.mark.asyncio
    async def test_process_job_dispatches_to_handler(self) -> None:
        """process_job should call the registered handler."""
        original = dict(HANDLERS)

        mock_handler = AsyncMock()
        HANDLERS["test_process"] = mock_handler

        job_data = {"type": "test_process", "id": "job-1", "payload": "test"}
        await process_job(job_data)

        mock_handler.assert_called_once_with(job_data)

        HANDLERS.clear()
        HANDLERS.update(original)

    @pytest.mark.asyncio
    async def test_process_job_handles_missing_type(self) -> None:
        """process_job should log error for jobs without type."""
        # Should not raise, just log
        await process_job({"data": "no type field"})

    @pytest.mark.asyncio
    async def test_process_job_handles_unknown_type(self) -> None:
        """process_job should log error for unregistered job types."""
        # Should not raise, just log
        await process_job({"type": "unknown_type_xyz"})

    @pytest.mark.asyncio
    async def test_process_job_catches_handler_errors(self) -> None:
        """process_job should catch and log handler exceptions."""
        original = dict(HANDLERS)

        async def failing_handler(data: dict) -> None:
            raise ValueError("Handler exploded")

        HANDLERS["failing_job"] = failing_handler

        # Should not raise -- error is caught and logged
        await process_job({"type": "failing_job", "id": "fail-1"})

        HANDLERS.clear()
        HANDLERS.update(original)
