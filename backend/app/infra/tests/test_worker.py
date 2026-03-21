"""Tests for the worker compatibility shim.

The custom poll-loop worker has been replaced by Celery. This file tests
that the shim module exports the expected constants and no-op functions
so existing imports don't break.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWorkerShim:
    def test_queue_constants_exist(self) -> None:
        """Queue name constants must still be importable for backward compatibility."""
        from app.infra.worker import (
            ALL_QUEUES,
            QUEUE_DOCUMENTS,
            QUEUE_INGESTION,
            QUEUE_KNOWLEDGE,
        )

        assert QUEUE_DOCUMENTS == "jobs:documents"
        assert QUEUE_INGESTION == "jobs:ingestion"
        assert QUEUE_KNOWLEDGE == "jobs:knowledge"
        assert set(ALL_QUEUES) == {QUEUE_DOCUMENTS, QUEUE_INGESTION, QUEUE_KNOWLEDGE}

    def test_register_handler_is_noop(self) -> None:
        """register_handler() must be a no-op (handlers now live in tasks.py)."""
        from app.infra.worker import register_handler

        # Must not raise and must return None
        result = register_handler("some_type", lambda x: x)
        assert result is None


class TestZombieJobCleanup:
    """Tests for _fail_zombie_ingestion_jobs() called on worker startup."""

    @pytest.mark.asyncio
    async def test_fails_active_jobs(self) -> None:
        """Should mark PENDING/SCANNING/PROCESSING jobs as FAILED."""
        from app.celery_app import _fail_zombie_ingestion_jobs

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.infra.database._session_factory", mock_factory):
            await _fail_zombie_ingestion_jobs()

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_active_jobs_skips_commit(self) -> None:
        """Should not commit when no zombie jobs exist."""
        from app.celery_app import _fail_zombie_ingestion_jobs

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.infra.database._session_factory", mock_factory):
            await _fail_zombie_ingestion_jobs()

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_session_factory_returns_early(self) -> None:
        """Should return immediately if _session_factory is None (DB not initialized)."""
        from app.celery_app import _fail_zombie_ingestion_jobs

        with patch("app.infra.database._session_factory", None):
            # Should not raise
            await _fail_zombie_ingestion_jobs()
