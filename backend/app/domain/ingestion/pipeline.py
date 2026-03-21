"""Stage-based ingestion pipeline with producer-consumer queues.

Architecture:
    Feeder -> download_q -> Download Workers (N)
                               -> extract_q -> Extract Workers (N)
                                                   -> embed_q -> Embed Workers (N)

Backpressure is controlled by queue maxsize. Each worker gets its own
DB session from the session factory to avoid concurrent session errors.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import sqlalchemy.exc
from sqlalchemy import select, text
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import (
    Document,
    DocumentChunk,
    DocumentSource,
    DocumentStatus,
)
from app.domain.documents.processors import get_processor
from app.domain.ingestion.drive_connector import (
    _GOOGLE_WORKSPACE_EXPORT_MAP,
    SUPPORTED_MIME_TYPES,
)
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.models import (
    IndexedFile,
    IndexedFileStage,
    IndexedFileStatus,
    IngestionJob,
    IngestionStatus,
)
from app.infra.llm import LLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types flowing through the pipeline queues
# ---------------------------------------------------------------------------


@dataclass
class DownloadResult:
    """Output of the download stage, input to the extract stage."""

    indexed_file_id: uuid.UUID
    drive_file_id: str
    file_name: str
    mime_type: str
    folder_path: str
    classification: dict[str, Any]
    file_bytes: bytes
    size_bytes: int


@dataclass
class ExtractResult:
    """Output of the extract stage, input to the embed stage."""

    indexed_file_id: uuid.UUID
    document_id: uuid.UUID
    document: Document
    chunks: list[DocumentChunk]


@dataclass
class PipelineConfig:
    """Configurable pipeline parameters."""

    download_workers: int = 5
    extract_workers: int = 3
    embed_workers: int = 2
    embed_batch_size: int = 100
    embed_max_retries: int = 2
    download_extract_max_retries: int = 2
    queue_multiplier: int = 2

    @classmethod
    def from_settings(cls) -> PipelineConfig:
        from app.config import get_settings

        s = get_settings()
        return cls(
            download_workers=s.pipeline_download_workers,
            extract_workers=s.pipeline_extract_workers,
            embed_workers=s.pipeline_embed_workers,
            embed_batch_size=s.pipeline_embed_batch_size,
            embed_max_retries=s.pipeline_embed_max_retries,
            download_extract_max_retries=s.pipeline_download_extract_max_retries,
            queue_multiplier=s.pipeline_queue_multiplier,
        )


@dataclass
class PipelineStats:
    """Mutable counters for pipeline progress."""

    downloaded: int = 0
    extracted: int = 0
    embedded: int = 0
    kg_done: int = 0
    failed: int = 0
    skipped: int = 0
    retry_succeeded: int = 0
    retry_failed: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def increment(self, **kwargs: int) -> None:
        async with self._lock:
            for key, delta in kwargs.items():
                setattr(self, key, getattr(self, key) + delta)

    def to_dict(self) -> dict[str, int]:
        return {
            "downloaded": self.downloaded,
            "extracted": self.extracted,
            "embedded": self.embedded,
            "kg_done": self.kg_done,
            "failed": self.failed,
            "skipped": self.skipped,
            "retry_succeeded": self.retry_succeeded,
            "retry_failed": self.retry_failed,
        }


# Sentinel to signal worker shutdown
_SENTINEL = None


class StagePipeline:
    """Stage-based ingestion pipeline with producer-consumer queues."""

    def __init__(
        self,
        session_factory: Any,
        connector: SourceConnector,
        llm: LLMProvider,
        job: IngestionJob,
        admin_user_id: uuid.UUID,
        config: PipelineConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._connector = connector
        self._llm = llm
        self._job = job
        self._admin_user_id = admin_user_id
        self._config = config or PipelineConfig.from_settings()

        c = self._config
        self._download_q: asyncio.Queue[IndexedFile | None] = asyncio.Queue(
            maxsize=c.download_workers * c.queue_multiplier
        )
        self._extract_q: asyncio.Queue[DownloadResult | None] = asyncio.Queue(
            maxsize=c.extract_workers * c.queue_multiplier
        )
        self._embed_q: asyncio.Queue[ExtractResult | None] = asyncio.Queue(
            maxsize=c.embed_workers * c.queue_multiplier
        )

        self._stats = PipelineStats()
        self._neo4j_client: Any = None  # task-local Neo4j client (lazy init)
        self._retry_file_ids: list[uuid.UUID] = []
        self._retry_lock = asyncio.Lock()

        # Counters for sentinel propagation between stages
        self._dl_done_count = 0
        self._dl_done_lock = asyncio.Lock()
        self._ext_done_count = 0
        self._ext_done_lock = asyncio.Lock()

    async def run(
        self,
        scanning_done: asyncio.Event,
        is_cancelled: Any = None,
    ) -> dict[str, Any]:
        """Run the full pipeline until all files are processed.

        Args:
            scanning_done: Event set when all scanners have finished.
            is_cancelled: Async callable returning True if job was cancelled.

        Returns:
            Dict with pipeline statistics.
        """
        c = self._config

        workers = [
            asyncio.create_task(self._feeder(scanning_done, is_cancelled), name="feeder"),
            *[
                asyncio.create_task(self._download_worker(i, is_cancelled), name=f"dl-{i}")
                for i in range(c.download_workers)
            ],
            *[
                asyncio.create_task(self._extract_worker(i, is_cancelled), name=f"ext-{i}")
                for i in range(c.extract_workers)
            ],
            *[
                asyncio.create_task(self._embed_worker(i, is_cancelled), name=f"emb-{i}")
                for i in range(c.embed_workers)
            ],
        ]

        try:
            await asyncio.gather(*workers)
        except Exception:
            logger.exception("Pipeline worker failed")
            for w in workers:
                w.cancel()
            raise
        finally:
            await self._close_neo4j()

        # Retry pass for all failed files (download, extract, embed, KG)
        if self._retry_file_ids:
            await self._retry_pass(is_cancelled)

        logger.info("Pipeline complete (job %s): %s", self._job.id, self._stats.to_dict())
        return self._stats.to_dict()

    # ------------------------------------------------------------------
    # Feeder: polls indexed_files and pushes to download queue
    # ------------------------------------------------------------------

    async def _feeder(
        self,
        scanning_done: asyncio.Event,
        is_cancelled: Any,
    ) -> None:
        """Poll indexed_files for pending rows and feed them to download workers.

        Uses short-lived sessions per poll cycle instead of holding one session
        open for the entire pipeline duration, which could exhaust the connection
        pool or get killed by pgbouncer.
        """
        poll_interval = 1.0

        while True:
            if is_cancelled and await is_cancelled():
                break

            async with self._session_factory() as db:
                rows = await self._fetch_pending(db, limit=20)

            if not rows:
                if scanning_done.is_set():
                    # Final drain
                    async with self._session_factory() as db:
                        rows = await self._fetch_pending(db, limit=20)
                    if not rows:
                        break
                else:
                    await asyncio.sleep(poll_interval)
                    continue

            for row in rows:
                await self._download_q.put(row)

        # Send sentinels to shut down download workers
        for _ in range(self._config.download_workers):
            await self._download_q.put(_SENTINEL)

    async def _fetch_pending(self, db: AsyncSession, limit: int = 20) -> list[IndexedFile]:
        """Fetch pending files and atomically mark them as downloading."""
        result = await db.execute(
            select(IndexedFile)
            .where(
                IndexedFile.job_id == self._job.id,
                IndexedFile.stage == IndexedFileStage.PENDING.value,
                IndexedFile.status != IndexedFileStatus.SKIPPED.value,
            )
            .order_by(IndexedFile.created_at)
            .limit(limit)
        )
        files = list(result.scalars().all())

        if files:
            ids = [f.id for f in files]
            await db.execute(
                sa_update(IndexedFile)
                .where(IndexedFile.id.in_(ids))
                .values(stage=IndexedFileStage.DOWNLOADING.value)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            for f in files:
                f.stage = IndexedFileStage.DOWNLOADING.value

        return files

    # ------------------------------------------------------------------
    # Stage 1: Download
    # ------------------------------------------------------------------

    async def _download_worker(self, worker_id: int, is_cancelled: Any) -> None:
        """Download files from Drive and push to extract queue."""
        try:
            while True:
                item = await self._download_q.get()
                if item is _SENTINEL:
                    break

                if is_cancelled and await is_cancelled():
                    break

                indexed_file: IndexedFile = item

                try:
                    result = await self._download_one(indexed_file)
                    if result is None:
                        # Skipped (too large, dedup, etc.)
                        continue
                    await self._extract_q.put(result)
                except Exception as e:
                    err_str = str(e)
                    # Google API errors that mean "file can't be exported" —
                    # skip instead of counting as a failure.
                    if any(skip in err_str for skip in self._SKIP_ERRORS):
                        logger.info(
                            "Skipping unexportable file %s: %s",
                            indexed_file.file_name,
                            err_str[:200],
                        )
                        await self._update_stage(
                            indexed_file.id,
                            IndexedFileStage.SKIPPED.value,
                            IndexedFileStatus.SKIPPED.value,
                            error_message=err_str[:500],
                        )
                        await self._stats.increment(skipped=1)
                        await self._increment_job_counter("skipped_files", 1)
                        continue

                    logger.warning(
                        "Download failed for %s (will retry): %s",
                        indexed_file.file_name,
                        e,
                    )
                    await self._update_stage(
                        indexed_file.id,
                        IndexedFileStage.FAILED.value,
                        IndexedFileStatus.FAILED.value,
                        error_message=err_str[:500],
                    )
                    async with self._retry_lock:
                        self._retry_file_ids.append(indexed_file.id)
        finally:
            # Last download worker to finish sends sentinels to extract workers
            async with self._dl_done_lock:
                self._dl_done_count += 1
                if self._dl_done_count == self._config.download_workers:
                    for _ in range(self._config.extract_workers):
                        await self._extract_q.put(_SENTINEL)

    # Google API errors that mean "skip this file", not "crash the job"
    _SKIP_ERRORS = ("exportSizeLimitExceeded", "fileNotExportable", "cannotExportFile")

    async def _download_one(self, indexed_file: IndexedFile) -> DownloadResult | None:
        """Download a single file. Returns None if skipped."""
        from app.config import get_settings

        # File size guard
        max_bytes = get_settings().max_ingest_file_size_mb * 1024 * 1024
        if indexed_file.size_bytes and indexed_file.size_bytes > max_bytes:
            logger.info("Skipping oversized file: %s", indexed_file.file_name)
            await self._update_stage(
                indexed_file.id,
                IndexedFileStage.SKIPPED.value,
                IndexedFileStatus.SKIPPED.value,
            )
            await self._stats.increment(skipped=1)
            await self._increment_job_counter("skipped_files", 1)
            return None

        # Dedup guard
        async with self._session_factory() as db:
            from sqlalchemy import or_ as sa_or

            existing = await db.execute(
                select(Document.id)
                .where(
                    Document.source == DocumentSource.GOOGLE_DRIVE,
                    Document.is_base_knowledge.is_(True),
                    sa_or(
                        Document.status == DocumentStatus.READY,
                        Document.status == DocumentStatus.PROCESSING,
                    ),
                    Document.metadata_["drive_file_id"].astext == indexed_file.drive_file_id,
                )
                .limit(1)
            )
            if existing.first() is not None:
                logger.info("Skipping already-ingested: %s", indexed_file.file_name)
                await self._update_stage(
                    indexed_file.id,
                    IndexedFileStage.SKIPPED.value,
                    IndexedFileStatus.SKIPPED.value,
                )
                await self._stats.increment(skipped=1)
                await self._increment_job_counter("skipped_files", 1)
                return None

        # Download
        file_bytes, filename = await self._connector.download_file(indexed_file.drive_file_id)

        await self._update_stage(indexed_file.id, IndexedFileStage.DOWNLOADED.value)
        await self._stats.increment(downloaded=1)

        logger.info("Downloaded %s (%d bytes)", indexed_file.file_name, len(file_bytes))

        return DownloadResult(
            indexed_file_id=indexed_file.id,
            drive_file_id=indexed_file.drive_file_id,
            file_name=filename,
            mime_type=indexed_file.mime_type,
            folder_path=indexed_file.folder_path,
            classification=indexed_file.classification or {},
            file_bytes=file_bytes,
            size_bytes=len(file_bytes),
        )

    # ------------------------------------------------------------------
    # Stage 2: Extract + Chunk
    # ------------------------------------------------------------------

    async def _extract_worker(self, worker_id: int, is_cancelled: Any) -> None:
        """Extract text, chunk, and commit Document records."""
        try:
            while True:
                item = await self._extract_q.get()
                if item is _SENTINEL:
                    break

                if is_cancelled and await is_cancelled():
                    break

                dl_result: DownloadResult = item

                try:
                    result = await self._extract_one(dl_result)
                    if result is not None:
                        await self._embed_q.put(result)
                except Exception as e:
                    logger.warning(
                        "Extract failed for %s (will retry): %s",
                        dl_result.file_name,
                        e,
                    )
                    await self._update_stage(
                        dl_result.indexed_file_id,
                        IndexedFileStage.FAILED.value,
                        IndexedFileStatus.FAILED.value,
                        error_message=str(e)[:500],
                    )
                    async with self._retry_lock:
                        self._retry_file_ids.append(dl_result.indexed_file_id)
                finally:
                    # Release file bytes regardless of outcome
                    dl_result.file_bytes = b""
                    gc.collect()
        finally:
            # Last extract worker to finish sends sentinels to embed workers
            async with self._ext_done_lock:
                self._ext_done_count += 1
                if self._ext_done_count == self._config.extract_workers:
                    for _ in range(self._config.embed_workers):
                        await self._embed_q.put(_SENTINEL)

    async def _extract_one(self, dl: DownloadResult) -> ExtractResult | None:
        """Extract text and create Document + chunks."""
        await self._update_stage(dl.indexed_file_id, IndexedFileStage.EXTRACTING.value)

        # Determine target MIME
        target_mime = dl.mime_type
        if dl.mime_type in _GOOGLE_WORKSPACE_EXPORT_MAP:
            target_mime = _GOOGLE_WORKSPACE_EXPORT_MAP[dl.mime_type][0]

        processor = get_processor(target_mime)
        if processor is None:
            file_ext = SUPPORTED_MIME_TYPES.get(dl.mime_type, "")
            processor = get_processor(file_ext)
        if processor is None:
            logger.warning("No processor for %s (%s)", dl.file_name, dl.mime_type)
            await self._update_stage(
                dl.indexed_file_id,
                IndexedFileStage.SKIPPED.value,
                IndexedFileStatus.SKIPPED.value,
            )
            await self._stats.increment(skipped=1)
            await self._increment_job_counter("skipped_files", 1)
            return None

        processing_result = await processor.process(dl.file_bytes)

        doc_id = uuid.uuid4()
        doc_metadata: dict[str, Any] = {
            "drive_file_id": dl.drive_file_id,
            "original_mime_type": dl.mime_type,
            "folder_path": dl.folder_path,
        }
        if dl.classification:
            doc_metadata["classification"] = dl.classification

        async with self._session_factory() as db:
            document = Document(
                id=doc_id,
                user_id=self._admin_user_id,
                filename=dl.file_name,
                file_type=target_mime,
                file_size=dl.size_bytes,
                storage_path=f"drive://{dl.drive_file_id}",
                status=DocumentStatus.PROCESSING,
                source=DocumentSource.GOOGLE_DRIVE,
                is_base_knowledge=True,
                expires_at=None,
                metadata_=doc_metadata,
            )
            db.add(document)
            await db.commit()
            await db.refresh(document)

            chunks_created: list[DocumentChunk] = []
            chunk_count = len(processing_result.chunks)
            result_metadata = processing_result.metadata

            for chunk_data in processing_result.chunks:
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_data.chunk_index,
                    content=chunk_data.content,
                    page_number=chunk_data.page_number,
                    token_count=len(chunk_data.content.split()),
                    metadata_=chunk_data.metadata,
                )
                db.add(chunk)
                chunks_created.append(chunk)

            # Free ChunkData pydantic objects — they held 182+ MB across files
            processing_result.chunks.clear()
            del processing_result

            await db.flush()

            document.status = DocumentStatus.READY
            document.chunk_count = chunk_count
            document.metadata_.update(result_metadata)
            document.processed_at = datetime.now(UTC)
            await db.commit()

        await self._update_stage(
            dl.indexed_file_id,
            IndexedFileStage.EXTRACTED.value,
            IndexedFileStatus.PROCESSING.value,
            document_id=doc_id,
        )
        await self._stats.increment(extracted=1)
        await self._increment_job_counter("processed_files", 1)

        logger.info("Extracted %s: %d chunks", dl.file_name, len(chunks_created))

        return ExtractResult(
            indexed_file_id=dl.indexed_file_id,
            document_id=doc_id,
            document=document,
            chunks=chunks_created,
        )

    # ------------------------------------------------------------------
    # Stage 3: Embed + KG (cross-file batching)
    # ------------------------------------------------------------------

    async def _embed_worker(self, worker_id: int, is_cancelled: Any) -> None:
        """Batch-embed chunks across files, then run KG extraction per file."""
        buffer: list[ExtractResult] = []
        chunk_count = 0

        while True:
            # Try to get with timeout so we can flush partial batches
            try:
                item = await asyncio.wait_for(self._embed_q.get(), timeout=2.0)
            except TimeoutError:
                if buffer:
                    await self._flush_embed_batch(buffer)
                    buffer.clear()
                    chunk_count = 0
                continue

            if item is _SENTINEL:
                # Flush remaining buffer and exit
                if buffer:
                    await self._flush_embed_batch(buffer)
                break

            if is_cancelled and await is_cancelled():
                break

            ext_result: ExtractResult = item
            buffer.append(ext_result)
            chunk_count += len(ext_result.chunks)

            # Flush when batch is large enough
            if chunk_count >= self._config.embed_batch_size or len(buffer) >= 5:
                await self._flush_embed_batch(buffer)
                buffer.clear()
                chunk_count = 0

    async def _flush_embed_batch(self, batch: list[ExtractResult]) -> None:
        """Embed all chunks in the batch with a single API call, then run KG per file."""
        if not batch:
            return

        # --- Cross-file batch embedding ---
        all_chunks: list[dict[str, Any]] = []
        chunk_to_doc: list[tuple[int, uuid.UUID]] = []  # (chunk_idx_in_all, doc_id)

        for ext in batch:
            await self._update_stage(ext.indexed_file_id, IndexedFileStage.EMBEDDING.value)
            for c in ext.chunks:
                all_chunks.append(
                    {
                        "id": c.id,
                        "content": c.content,
                        "metadata": c.metadata_ or {},
                    }
                )
                chunk_to_doc.append((len(all_chunks) - 1, ext.document_id))

        embed_success = False
        if all_chunks:
            try:
                async with self._session_factory() as db:
                    from app.domain.knowledge.vector_service import VectorService

                    vector_service = VectorService(db=db)
                    count = await vector_service.embed_chunks(
                        chunks=all_chunks,
                        document_id=batch[0].document_id,
                    )
                    await db.commit()
                    logger.info(
                        "Batch embedded %d chunks across %d files",
                        count,
                        len(batch),
                    )
                    embed_success = True
            except Exception as e:
                logger.error("Batch embedding failed (non-fatal): %s", e)

        # --- Per-file KG extraction ---
        for ext in batch:
            if embed_success:
                await self._update_stage(ext.indexed_file_id, IndexedFileStage.EMBEDDED.value)
                await self._stats.increment(embedded=1)

            kg_success = await self._extract_kg_for_file(ext)

            if embed_success and kg_success:
                await self._update_stage(
                    ext.indexed_file_id,
                    IndexedFileStage.KG_DONE.value,
                    IndexedFileStatus.COMPLETED.value,
                )
                await self._stats.increment(kg_done=1)
            elif embed_success and not kg_success:
                await self._update_stage(ext.indexed_file_id, IndexedFileStage.KG_FAILED.value)
                async with self._retry_lock:
                    self._retry_file_ids.append(ext.indexed_file_id)
            elif not embed_success:
                await self._update_stage(ext.indexed_file_id, IndexedFileStage.EMBED_FAILED.value)
                async with self._retry_lock:
                    self._retry_file_ids.append(ext.indexed_file_id)

            # Release chunk references
            ext.chunks = []

        gc.collect()

    async def _get_neo4j(self) -> Any:
        """Get or create a task-local Neo4j client.

        The global neo4j_client singleton is bound to the event loop from
        worker startup. Celery tasks run in their own asyncio.run() loop,
        so we need a fresh client bound to the current loop.
        """
        if self._neo4j_client is None:
            from app.infra.neo4j_client import Neo4jClient

            self._neo4j_client = Neo4jClient()
            await self._neo4j_client.connect()
        return self._neo4j_client

    async def _close_neo4j(self) -> None:
        """Close the task-local Neo4j client if one was created."""
        if self._neo4j_client is not None:
            try:
                await self._neo4j_client.close()
            except Exception:
                pass
            self._neo4j_client = None

    async def _extract_kg_for_file(self, ext: ExtractResult) -> bool:
        """Run KG extraction for a single file's chunks. Returns True on success."""
        if not ext.chunks:
            return True

        try:
            async with self._session_factory() as db:
                from app.domain.knowledge.graph_service import GraphService
                from app.domain.knowledge.kg_builder import KGBuilder

                neo4j = await self._get_neo4j()
                graph_service = GraphService(db=db, neo4j=neo4j)
                kg_builder = KGBuilder(graph_service=graph_service, llm=self._llm)

                chunk_dicts = [
                    {"content": c.content, "metadata": c.metadata_ or {}} for c in ext.chunks
                ]
                result = await kg_builder.build_from_chunks(
                    chunks=chunk_dicts, document_id=ext.document_id
                )
                await db.commit()
                logger.info(
                    "KG for %s: %d entities, %d rels",
                    ext.document_id,
                    result.get("entities_created", 0),
                    result.get("relationships_created", 0),
                )
                return True
        except Exception as e:
            logger.error(
                "KG extraction failed for %s (non-fatal): %s",
                ext.document_id,
                e,
            )
            return False

    # ------------------------------------------------------------------
    # Retry pass
    # ------------------------------------------------------------------

    async def _retry_pass(self, is_cancelled: Any) -> None:
        """Re-attempt failed files with exponential backoff.

        Handles all failure types:
        - FAILED (download/extract): re-downloads and re-processes from scratch
        - EMBED_FAILED / KG_FAILED: re-embeds and re-runs KG from existing chunks
        """
        logger.info("Retry pass: %d files to retry", len(self._retry_file_ids))

        _REDOWNLOAD_STAGES = {
            IndexedFileStage.FAILED.value,
            IndexedFileStage.DOWNLOADING.value,
        }
        _RE_EMBED_STAGES = {
            IndexedFileStage.EMBED_FAILED.value,
            IndexedFileStage.KG_FAILED.value,
        }

        async with self._session_factory() as db:
            for file_id in self._retry_file_ids:
                if is_cancelled and await is_cancelled():
                    break

                result = await db.execute(select(IndexedFile).where(IndexedFile.id == file_id))
                indexed_file = result.scalar_one_or_none()
                if not indexed_file:
                    continue

                stage = indexed_file.stage
                if stage in _REDOWNLOAD_STAGES:
                    max_retries = self._config.download_extract_max_retries
                else:
                    max_retries = self._config.embed_max_retries

                if indexed_file.retry_count >= max_retries:
                    logger.info(
                        "Max retries (%d) reached for %s (stage=%s)",
                        max_retries,
                        indexed_file.file_name,
                        stage,
                    )
                    await self._stats.increment(retry_failed=1)
                    await self._stats.increment(failed=1)
                    await self._increment_job_counter("failed_files", 1)
                    continue

                # Increment retry count + exponential backoff delay
                new_count = indexed_file.retry_count + 1
                await db.execute(
                    sa_update(IndexedFile)
                    .where(IndexedFile.id == file_id)
                    .values(retry_count=new_count)
                    .execution_options(synchronize_session=False)
                )
                await db.commit()

                backoff = min(2**indexed_file.retry_count, 30)
                logger.info(
                    "Retry %d/%d for %s (stage=%s, backoff=%.0fs)",
                    new_count,
                    max_retries,
                    indexed_file.file_name,
                    stage,
                    backoff,
                )
                await asyncio.sleep(backoff)

                if stage in _REDOWNLOAD_STAGES:
                    success = await self._retry_download_extract(indexed_file)
                elif stage in _RE_EMBED_STAGES:
                    success = await self._retry_embed_kg(db, indexed_file)
                else:
                    # Unknown failed stage — try re-download as a fallback
                    success = await self._retry_download_extract(indexed_file)

                if success:
                    await self._stats.increment(retry_succeeded=1)
                else:
                    await self._stats.increment(retry_failed=1)

    async def _retry_download_extract(self, indexed_file: IndexedFile) -> bool:
        """Re-download and re-process a file that failed at download or extract."""
        try:
            # Reset stage to downloading
            await self._update_stage(
                indexed_file.id,
                IndexedFileStage.DOWNLOADING.value,
                IndexedFileStatus.PROCESSING.value,
            )

            dl_result = await self._download_one(indexed_file)
            if dl_result is None:
                # Skipped (dedup, size, etc.)
                return True

            ext_result = await self._extract_one(dl_result)
            dl_result.file_bytes = b""
            if ext_result is None:
                return True

            await self._flush_embed_batch([ext_result])

            # Check final stage
            async with self._session_factory() as db:
                refreshed = await db.execute(
                    select(IndexedFile.stage).where(IndexedFile.id == indexed_file.id)
                )
                final_stage = refreshed.scalar_one_or_none()
                return final_stage == IndexedFileStage.KG_DONE.value
        except Exception as e:
            logger.error(
                "Retry download/extract failed for %s: %s",
                indexed_file.file_name,
                e,
            )
            await self._update_stage(
                indexed_file.id,
                IndexedFileStage.FAILED.value,
                IndexedFileStatus.FAILED.value,
                error_message=str(e)[:500],
            )
            return False

    async def _retry_embed_kg(self, db: AsyncSession, indexed_file: IndexedFile) -> bool:
        """Re-embed and re-run KG for a file that already has chunks."""
        if not indexed_file.document_id:
            await self._stats.increment(failed=1)
            await self._increment_job_counter("failed_files", 1)
            return False

        doc_result = await db.execute(
            select(Document).where(Document.id == indexed_file.document_id)
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            await self._stats.increment(failed=1)
            await self._increment_job_counter("failed_files", 1)
            return False

        chunk_result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = list(chunk_result.scalars().all())

        ext = ExtractResult(
            indexed_file_id=indexed_file.id,
            document_id=document.id,
            document=document,
            chunks=chunks,
        )

        await self._flush_embed_batch([ext])

        refreshed = await db.execute(
            select(IndexedFile.stage).where(IndexedFile.id == indexed_file.id)
        )
        stage = refreshed.scalar_one_or_none()
        return stage == IndexedFileStage.KG_DONE.value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _update_stage(
        self,
        indexed_file_id: uuid.UUID,
        stage: str,
        status: str | None = None,
        document_id: uuid.UUID | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an indexed file's pipeline stage (and optionally status).

        Retries once on connection errors to handle pgbouncer drops.
        Never raises — logs errors so callers in except blocks don't crash.
        """
        values: dict[str, Any] = {"stage": stage}
        if status is not None:
            values["status"] = status
        if document_id is not None:
            values["document_id"] = document_id
        if error_message is not None:
            values["error_message"] = error_message
        if stage in (
            IndexedFileStage.KG_DONE.value,
            IndexedFileStage.FAILED.value,
            IndexedFileStage.SKIPPED.value,
            IndexedFileStage.EMBED_FAILED.value,
            IndexedFileStage.KG_FAILED.value,
        ):
            values["processed_at"] = datetime.now(UTC)

        for attempt in range(2):
            try:
                async with self._session_factory() as db:
                    await db.execute(
                        sa_update(IndexedFile)
                        .where(IndexedFile.id == indexed_file_id)
                        .values(**values)
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
                return
            except (OSError, sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError):
                if attempt == 0:
                    logger.warning(
                        "DB error updating stage for %s (attempt 1), retrying",
                        indexed_file_id,
                    )
                    await asyncio.sleep(0.5)
                else:
                    logger.error(
                        "DB error updating stage for %s (attempt 2), giving up: stage=%s status=%s",
                        indexed_file_id,
                        stage,
                        status,
                        exc_info=True,
                    )

    async def _increment_job_counter(self, column: str, delta: int) -> None:
        """Atomically increment a job progress counter.

        Never raises — logs errors so callers in except blocks don't crash.
        """
        col = getattr(IngestionJob, column)
        try:
            async with self._session_factory() as db:
                await db.execute(
                    sa_update(IngestionJob)
                    .where(
                        IngestionJob.id == self._job.id,
                        IngestionJob.status != IngestionStatus.CANCELLED,
                    )
                    .values(**{column: col + delta})
                    .execution_options(synchronize_session=False)
                )
                await db.commit()
        except Exception:
            logger.warning(
                "Failed to increment job counter %s for job %s",
                column,
                self._job.id,
                exc_info=True,
            )

    async def _update_job_stage_counts(self) -> None:
        """Update job metadata with per-stage counts for observability."""
        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT stage, COUNT(*) as cnt
                    FROM indexed_files
                    WHERE job_id = :job_id
                    GROUP BY stage
                """),
                {"job_id": str(self._job.id)},
            )
            stage_counts = {row[0]: row[1] for row in result.fetchall()}

            self._job.metadata_["stage_counts"] = stage_counts
            self._job.metadata_["pipeline_stats"] = self._stats.to_dict()

            await db.execute(
                sa_update(IngestionJob)
                .where(
                    IngestionJob.id == self._job.id,
                    IngestionJob.status != IngestionStatus.CANCELLED,
                )
                .values(metadata_=self._job.metadata_)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
