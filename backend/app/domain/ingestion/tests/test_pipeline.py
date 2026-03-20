"""Tests for the stage-based ingestion pipeline."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.ingestion.models import (
    IndexedFile,
    IndexedFileStage,
    IndexedFileStatus,
    IngestionJob,
    IngestionStatus,
)
from app.domain.ingestion.pipeline import (
    DownloadResult,
    ExtractResult,
    PipelineConfig,
    PipelineStats,
    StagePipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(**kwargs) -> IngestionJob:
    defaults = {
        "id": uuid.uuid4(),
        "triggered_by": uuid.uuid4(),
        "source": "google_drive",
        "status": IngestionStatus.PROCESSING,
        "folder_id": "root",
        "total_files": 0,
        "processed_files": 0,
        "failed_files": 0,
        "skipped_files": 0,
        "error_message": None,
        "metadata_": {},
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
    }
    defaults.update(kwargs)
    job = MagicMock(spec=IngestionJob)
    for k, v in defaults.items():
        setattr(job, k, v)
    return job


def _make_indexed_file(**kwargs) -> IndexedFile:
    defaults = {
        "id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
        "drive_file_id": f"drive-{uuid.uuid4().hex[:8]}",
        "file_name": "test.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1024,
        "folder_path": "Test/Folder",
        "classification": {"major": "CS"},
        "status": IndexedFileStatus.PENDING.value,
        "stage": IndexedFileStage.PENDING.value,
        "retry_count": 0,
        "document_id": None,
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "processed_at": None,
    }
    defaults.update(kwargs)
    f = MagicMock(spec=IndexedFile)
    for k, v in defaults.items():
        setattr(f, k, v)
    return f


def _make_session_factory():
    """Create a mock session factory."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.first.return_value = None
    mock_result.fetchall.return_value = []
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result

    @asynccontextmanager
    async def factory():
        yield mock_db

    return factory, mock_db


def _small_config() -> PipelineConfig:
    """Pipeline config with minimal workers for testing."""
    return PipelineConfig(
        download_workers=1,
        extract_workers=1,
        embed_workers=1,
        embed_batch_size=10,
        embed_max_retries=2,
        queue_multiplier=2,
    )


# ---------------------------------------------------------------------------
# PipelineStats
# ---------------------------------------------------------------------------


class TestPipelineStats:

    @pytest.mark.asyncio
    async def test_increment_and_to_dict(self) -> None:
        stats = PipelineStats()
        await stats.increment(downloaded=3, extracted=2)
        await stats.increment(failed=1)
        d = stats.to_dict()
        assert d["downloaded"] == 3
        assert d["extracted"] == 2
        assert d["failed"] == 1
        assert d["embedded"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_increments(self) -> None:
        stats = PipelineStats()
        tasks = [stats.increment(downloaded=1) for _ in range(100)]
        await asyncio.gather(*tasks)
        assert stats.downloaded == 100


# ---------------------------------------------------------------------------
# PipelineConfig
# ---------------------------------------------------------------------------


class TestPipelineConfig:

    def test_from_settings(self) -> None:
        with patch("app.domain.ingestion.pipeline.PipelineConfig.from_settings") as mock:
            mock.return_value = _small_config()
            config = PipelineConfig.from_settings()
            assert config.download_workers == 1


# ---------------------------------------------------------------------------
# StagePipeline - Download
# ---------------------------------------------------------------------------


class TestDownloadStage:

    @pytest.mark.asyncio
    async def test_download_skips_oversized_files(self) -> None:
        """Files exceeding max size should be skipped without downloading."""
        factory, mock_db = _make_session_factory()
        job = _make_job()
        connector = AsyncMock()
        llm = MagicMock()

        pipeline = StagePipeline(
            session_factory=factory,
            connector=connector,
            llm=llm,
            job=job,
            admin_user_id=uuid.uuid4(),
            config=_small_config(),
        )

        # File larger than 50MB limit
        indexed_file = _make_indexed_file(
            size_bytes=100 * 1024 * 1024,  # 100MB
            job_id=job.id,
        )

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.max_ingest_file_size_mb = 50
            result = await pipeline._download_one(indexed_file)

        assert result is None
        assert pipeline._stats.skipped == 1

    @pytest.mark.asyncio
    async def test_download_skips_already_ingested(self) -> None:
        """Files that already exist as documents should be skipped."""
        factory, mock_db = _make_session_factory()
        # Make dedup check return an existing document
        mock_result = MagicMock()
        mock_result.first.return_value = (uuid.uuid4(),)
        mock_db.execute.return_value = mock_result

        job = _make_job()
        connector = AsyncMock()
        llm = MagicMock()

        pipeline = StagePipeline(
            session_factory=factory,
            connector=connector,
            llm=llm,
            job=job,
            admin_user_id=uuid.uuid4(),
            config=_small_config(),
        )

        indexed_file = _make_indexed_file(
            size_bytes=1024,
            job_id=job.id,
        )

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.max_ingest_file_size_mb = 50
            result = await pipeline._download_one(indexed_file)

        assert result is None
        assert pipeline._stats.skipped == 1
        # Should NOT have called download_file
        connector.download_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_returns_result(self) -> None:
        """Successful download should return a DownloadResult."""
        factory, mock_db = _make_session_factory()
        job = _make_job()
        connector = AsyncMock()
        connector.download_file.return_value = (b"pdf-content", "test.pdf")
        llm = MagicMock()

        pipeline = StagePipeline(
            session_factory=factory,
            connector=connector,
            llm=llm,
            job=job,
            admin_user_id=uuid.uuid4(),
            config=_small_config(),
        )

        indexed_file = _make_indexed_file(
            size_bytes=1024,
            job_id=job.id,
        )

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.max_ingest_file_size_mb = 50
            result = await pipeline._download_one(indexed_file)

        assert result is not None
        assert isinstance(result, DownloadResult)
        assert result.file_bytes == b"pdf-content"
        assert result.file_name == "test.pdf"
        assert pipeline._stats.downloaded == 1


# ---------------------------------------------------------------------------
# StagePipeline - Full pipeline (integration-style)
# ---------------------------------------------------------------------------


class TestPipelineIntegration:

    @pytest.mark.asyncio
    async def test_empty_pipeline_completes(self) -> None:
        """Pipeline with no files should complete without errors."""
        factory, mock_db = _make_session_factory()
        job = _make_job()
        connector = AsyncMock()
        llm = MagicMock()

        pipeline = StagePipeline(
            session_factory=factory,
            connector=connector,
            llm=llm,
            job=job,
            admin_user_id=uuid.uuid4(),
            config=_small_config(),
        )

        scanning_done = asyncio.Event()
        scanning_done.set()  # No scanning happening

        result = await pipeline.run(scanning_done)
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_cancellation_stops_pipeline(self) -> None:
        """Pipeline should stop when cancellation is detected."""
        factory, mock_db = _make_session_factory()
        job = _make_job()
        connector = AsyncMock()
        llm = MagicMock()

        pipeline = StagePipeline(
            session_factory=factory,
            connector=connector,
            llm=llm,
            job=job,
            admin_user_id=uuid.uuid4(),
            config=_small_config(),
        )

        scanning_done = asyncio.Event()
        scanning_done.set()

        cancel_called = False

        async def is_cancelled():
            nonlocal cancel_called
            cancel_called = True
            return True

        result = await pipeline.run(scanning_done, is_cancelled=is_cancelled)
        assert cancel_called


# ---------------------------------------------------------------------------
# StagePipeline - Embed batching
# ---------------------------------------------------------------------------


class TestEmbedBatching:

    @pytest.mark.asyncio
    async def test_flush_embed_batch_calls_vector_service(self) -> None:
        """Flushing an embed batch should call VectorService.embed_chunks."""
        factory, mock_db = _make_session_factory()
        job = _make_job()
        connector = AsyncMock()
        llm = MagicMock()

        pipeline = StagePipeline(
            session_factory=factory,
            connector=connector,
            llm=llm,
            job=job,
            admin_user_id=uuid.uuid4(),
            config=_small_config(),
        )

        # Create mock extract results with chunks
        doc_id = uuid.uuid4()
        mock_chunk = MagicMock()
        mock_chunk.id = uuid.uuid4()
        mock_chunk.content = "test content"
        mock_chunk.metadata_ = {}

        ext_result = ExtractResult(
            indexed_file_id=uuid.uuid4(),
            document_id=doc_id,
            document=MagicMock(),
            chunks=[mock_chunk],
        )

        mock_neo4j = AsyncMock()

        with patch(
            "app.domain.knowledge.vector_service.VectorService"
        ) as MockVS, patch(
            "app.domain.knowledge.graph_service.GraphService"
        ), patch(
            "app.domain.knowledge.kg_builder.KGBuilder"
        ) as MockKG:
            mock_vs_instance = AsyncMock()
            mock_vs_instance.embed_chunks.return_value = 1
            MockVS.return_value = mock_vs_instance

            mock_kg_instance = AsyncMock()
            mock_kg_instance.build_from_chunks.return_value = {
                "entities_created": 2,
                "relationships_created": 1,
            }
            MockKG.return_value = mock_kg_instance

            pipeline._get_neo4j = AsyncMock(return_value=mock_neo4j)
            await pipeline._flush_embed_batch([ext_result])

        mock_vs_instance.embed_chunks.assert_called_once()
        assert pipeline._stats.embedded == 1
        assert pipeline._stats.kg_done == 1
