"""Tests for ingestion service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.ingestion.exceptions import (
    IngestionAlreadyRunningError,
    IngestionJobNotFoundError,
)
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import TriggerIngestionRequest
from app.domain.ingestion.service import IngestionService


def _make_job(**kwargs) -> MagicMock:
    """Create a mock IngestionJob."""
    defaults = {
        "id": uuid.uuid4(),
        "triggered_by": uuid.uuid4(),
        "source": "google_drive",
        "status": IngestionStatus.COMPLETED,
        "folder_id": None,
        "total_files": 5,
        "processed_files": 4,
        "failed_files": 1,
        "skipped_files": 0,
        "error_message": None,
        "metadata_": {},
        "metadata": {},
        "started_at": datetime.now(UTC),
        "completed_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    job = MagicMock(spec=IngestionJob)
    for k, v in defaults.items():
        setattr(job, k, v)
    return job


class TestGetJob:
    """Test getting a single job."""

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """Should raise error when job not found."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = IngestionService(db=mock_db, storage=AsyncMock())
        with pytest.raises(IngestionJobNotFoundError):
            await service.get_job(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """Should return job when found."""
        job = _make_job()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        service = IngestionService(db=mock_db, storage=AsyncMock())
        result = await service.get_job(job.id)
        assert result.id == job.id


class TestListJobs:
    """Test listing jobs."""

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        """Should return empty list when no jobs."""
        mock_db = AsyncMock()
        # Count query
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        # List query
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count, mock_list]

        service = IngestionService(db=mock_db, storage=AsyncMock())
        result = await service.list_jobs()
        assert result.total == 0
        assert len(result.items) == 0


class TestCancelJob:
    """Test cancelling a job."""

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """Should raise error when job not found."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = IngestionService(db=mock_db, storage=AsyncMock())
        with pytest.raises(IngestionJobNotFoundError):
            await service.cancel_job(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_running(self) -> None:
        """Should cancel a running job."""
        job = _make_job(status=IngestionStatus.PROCESSING)
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        service = IngestionService(db=mock_db, storage=AsyncMock())
        result = await service.cancel_job(job.id)
        assert result.status == IngestionStatus.CANCELLED.value


class TestTriggerIngestion:
    """Test triggering a new ingestion job."""

    @pytest.mark.asyncio
    async def test_already_running(self) -> None:
        """Should raise error if a genuinely active job exists."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        # 1st call: stale-job UPDATE (no stale jobs found)
        mock_stale_result = MagicMock()
        mock_stale_result.rowcount = 0
        # 2nd call: SELECT for active jobs — finds a running one
        mock_running_result = MagicMock()
        mock_running_result.scalar_one_or_none.return_value = _make_job(
            status=IngestionStatus.PROCESSING,
        )
        mock_db.execute.side_effect = [mock_stale_result, mock_running_result]

        service = IngestionService(db=mock_db, storage=AsyncMock())
        with pytest.raises(IngestionAlreadyRunningError):
            await service.trigger_ingestion(
                TriggerIngestionRequest(),
                admin_user_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_stale_job_auto_failed(self) -> None:
        """Stale zombie jobs should be auto-failed so trigger succeeds."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        # 1st call: stale-job UPDATE — 1 row updated (zombie cleared)
        mock_stale_result = MagicMock()
        mock_stale_result.rowcount = 1
        # 2nd call: SELECT for active jobs — none found (zombie was cleared)
        mock_running_result = MagicMock()
        mock_running_result.scalar_one_or_none.return_value = None
        # 3rd call: SELECT AppConfig for default folder — no saved default
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_stale_result, mock_running_result, mock_config_result]

        # After db.add + commit, refresh populates the job fields
        async def _fake_refresh(obj: IngestionJob) -> None:
            obj.id = uuid.uuid4()
            obj.total_files = 0
            obj.processed_files = 0
            obj.failed_files = 0
            obj.skipped_files = 0
            obj.metadata_ = {}
            obj.started_at = datetime.now(UTC)
            obj.completed_at = None

        mock_db.refresh = AsyncMock(side_effect=_fake_refresh)

        service = IngestionService(db=mock_db, storage=AsyncMock())

        with patch("app.domain.ingestion.service.get_settings") as mock_settings:
            mock_settings.return_value.google_drive_folder_id = "test-folder"
            with patch("app.domain.ingestion.tasks.run_ingestion_task") as mock_task:
                await service.trigger_ingestion(
                    TriggerIngestionRequest(),
                    admin_user_id=uuid.uuid4(),
                )

        # Stale-job commit was called (at least once for stale + once for new job)
        assert mock_db.commit.await_count >= 2
        # A new job was created
        mock_db.add.assert_called_once()
        # Celery task was dispatched
        mock_task.delay.assert_called_once()
