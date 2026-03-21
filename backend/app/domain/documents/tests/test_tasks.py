"""Tests for Celery document tasks."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch


class TestProcessDocumentTask:
    def test_task_is_registered(self) -> None:
        """Task must be importable and registered with Celery."""
        from app.domain.documents.tasks import process_document_task

        assert process_document_task is not None
        assert process_document_task.name == "app.domain.documents.tasks.process_document_task"

    def test_task_queue_route(self) -> None:
        """Task name must match the documents queue route prefix."""
        from app.domain.documents.tasks import process_document_task

        assert process_document_task.name.startswith("app.domain.documents.tasks.")

    @patch("app.domain.documents.service.DocumentService", autospec=True)
    @patch("app.domain.documents.tasks.storage_client")
    @patch("app.domain.documents.tasks.get_db_session")
    def test_process_document_calls_service(
        self,
        mock_get_db: MagicMock,
        mock_storage: MagicMock,
        mock_service_cls: MagicMock,
    ) -> None:
        """process_document_task must call DocumentService.process_document with correct UUID."""
        from app.domain.documents.tasks import process_document_task

        document_id = str(uuid.uuid4())

        mock_db = AsyncMock()

        async def _fake_db_gen():
            yield mock_db

        mock_get_db.return_value = _fake_db_gen()

        mock_service = AsyncMock()
        mock_service_cls.return_value = mock_service

        # Call the sync task directly (it calls asyncio.run internally)
        process_document_task.run(document_id=document_id)

        mock_service.process_document.assert_awaited_once_with(uuid.UUID(document_id))


class TestCleanupExpiredTask:
    def test_task_is_registered(self) -> None:
        from app.domain.documents.tasks import cleanup_expired_task

        assert cleanup_expired_task is not None
        assert cleanup_expired_task.name == "app.domain.documents.tasks.cleanup_expired_task"

    @patch("app.domain.documents.service.DocumentService", autospec=True)
    @patch("app.domain.documents.tasks.storage_client")
    @patch("app.domain.documents.tasks.get_db_session")
    def test_cleanup_calls_service(
        self,
        mock_get_db: MagicMock,
        mock_storage: MagicMock,
        mock_service_cls: MagicMock,
    ) -> None:
        from app.domain.documents.tasks import cleanup_expired_task

        mock_db = AsyncMock()

        async def _fake_db_gen():
            yield mock_db

        mock_get_db.return_value = _fake_db_gen()

        mock_service = AsyncMock()
        mock_service_cls.return_value = mock_service

        cleanup_expired_task.run()

        mock_service.cleanup_expired.assert_awaited_once()
