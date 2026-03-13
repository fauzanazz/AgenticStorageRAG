"""Tests for ingestion service."""

import uuid
from datetime import datetime, timezone
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
        "started_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
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
        """Should raise error if job is already running."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_job(status=IngestionStatus.PROCESSING)
        mock_db.execute.return_value = mock_result

        service = IngestionService(db=mock_db, storage=AsyncMock())
        with pytest.raises(IngestionAlreadyRunningError):
            await service.trigger_ingestion(
                TriggerIngestionRequest(),
                admin_user_id=uuid.uuid4(),
            )
