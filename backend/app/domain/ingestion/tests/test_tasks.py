"""Tests for Celery ingestion tasks."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch


class TestRunIngestionTask:
    def test_task_is_registered(self) -> None:
        """Task must be importable and registered with Celery."""
        from app.domain.ingestion.tasks import run_ingestion_task

        assert run_ingestion_task is not None
        assert (
            run_ingestion_task.name
            == "app.domain.ingestion.tasks.run_ingestion_task"
        )

    def test_task_queue_route(self) -> None:
        """Task name must match the ingestion queue route prefix."""
        from app.domain.ingestion.tasks import run_ingestion_task

        assert run_ingestion_task.name.startswith("app.domain.ingestion.tasks.")

    @patch("app.domain.ingestion.orchestrator.IngestionOrchestrator", autospec=True)
    @patch("app.domain.ingestion.drive_connector.GoogleDriveConnector", autospec=True)
    @patch("app.domain.ingestion.tasks.storage_client")
    @patch("app.domain.ingestion.tasks.llm_provider")
    def test_run_ingestion_calls_orchestrator(
        self,
        mock_llm: MagicMock,
        mock_storage: MagicMock,
        mock_connector_cls: MagicMock,
        mock_orchestrator_cls: MagicMock,
    ) -> None:
        """run_ingestion_task must instantiate orchestrator and call .run()."""
        from app.domain.ingestion.tasks import run_ingestion_task

        job_id = str(uuid.uuid4())
        admin_user_id = str(uuid.uuid4())

        # Mock a fresh engine + session factory returned by build_session_factory
        mock_engine = AsyncMock()
        mock_engine.url = "postgresql+asyncpg://test/db"

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory = MagicMock(return_value=mock_ctx)

        mock_job = MagicMock()
        mock_db.get = AsyncMock(return_value=mock_job)

        mock_orchestrator = AsyncMock()
        mock_orchestrator_cls.return_value = mock_orchestrator

        with (
            patch("app.infra.database._engine", mock_engine),
            patch(
                "app.infra.database.build_session_factory",
                return_value=(mock_engine, mock_session_factory),
            ),
        ):
            run_ingestion_task.run(job_id=job_id, admin_user_id=admin_user_id, force=False)

        mock_orchestrator.run.assert_awaited_once_with(
            job=mock_job,
            admin_user_id=uuid.UUID(admin_user_id),
            force=False,
        )

    @patch("app.infra.database._engine", None)
    def test_run_ingestion_handles_missing_db(self) -> None:
        """Task must log and return gracefully when DB is not initialised."""
        from app.domain.ingestion.tasks import run_ingestion_task

        # Should not raise — just log error and return
        run_ingestion_task.run(
            job_id=str(uuid.uuid4()),
            admin_user_id=str(uuid.uuid4()),
            force=False,
        )
