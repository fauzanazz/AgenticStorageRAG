"""Tools for the ingestion orchestrator agent.

Each tool is a callable that the LLM agent can invoke via tool_use.
Tools handle Drive scanning, LLM-based metadata classification,
file ingestion (download + process + embed + KG), and progress tracking.

Concurrency model
~~~~~~~~~~~~~~~~~
- ``IngestFileTool.execute()`` is the atomic per-file unit (single file).
- ``BatchIngestFilesTool.execute()`` fans out a list of files using
  ``asyncio.gather`` bounded by a ``Semaphore(FILE_CONCURRENCY)``.
  The orchestrator agent uses this to process batches in parallel.
- Each worker container handles one ingestion job at a time; job-level
  parallelism is achieved by running multiple worker replicas
  (docker-compose ``deploy.replicas``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import (
    Document,
    DocumentChunk,
    DocumentSource,
    DocumentStatus,
)
from app.domain.documents.processors import get_processor
from app.domain.ingestion.drive_connector import SUPPORTED_MIME_TYPES
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.schemas import (
    DriveFolderEntry,
    FileMetadataClassification,
)
from app.infra.llm import LLMProvider
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base tool interface
# ---------------------------------------------------------------------------


class OrchestratorTool(ABC):
    """Base class for orchestrator agent tools.

    Each tool defines its name, description, and JSON Schema parameters
    so the LLM can call it via native tool_use.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name used in LLM tool_use calls."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description shown to the LLM."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema for the tool's input parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the tool and return a JSON-serialisable result dict."""
        ...

    def to_tool_spec(self) -> dict[str, Any]:
        """Return the LiteLLM / Anthropic tool specification."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


# ---------------------------------------------------------------------------
# 1. scan_folder
# ---------------------------------------------------------------------------


class ScanFolderTool(OrchestratorTool):
    """Lists every direct child (files + subfolders) of a Drive folder.

    The orchestrator uses this to explore the folder tree level-by-level,
    deciding dynamically which subfolders to recurse into.
    """

    def __init__(self, connector: SourceConnector) -> None:
        self._connector = connector

    @property
    def name(self) -> str:
        return "scan_folder"

    @property
    def description(self) -> str:
        return (
            "List all direct children (files and subfolders) of a Google Drive folder. "
            "Returns file name, MIME type, size, and whether it is a folder. "
            "Use this to explore the folder tree and decide which subfolders to enter."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Google Drive folder ID to scan.",
                },
            },
            "required": ["folder_id"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        folder_id: str = kwargs["folder_id"]

        entries: list[DriveFolderEntry] = (
            await self._connector.list_folder_children(folder_id)
        )

        children = []
        for e in entries:
            child: dict[str, Any] = {
                "file_id": e.file_id,
                "name": e.name,
                "mime_type": e.mime_type,
                "is_folder": e.is_folder,
            }
            if e.size is not None:
                child["size_bytes"] = e.size
            children.append(child)

        return {
            "folder_id": folder_id,
            "children_count": len(children),
            "folders": [c for c in children if c["is_folder"]],
            "files": [c for c in children if not c["is_folder"]],
        }


# ---------------------------------------------------------------------------
# 2. classify_file
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT = """You are a metadata classification expert. Given a file name and its full folder path in a Google Drive, extract structured metadata.

You MUST return ONLY valid JSON with this exact structure:
{
    "major": "Academic major or department name, or null",
    "course_code": "Course code like IF2120, or null",
    "course_name": "Full course name, or null",
    "year": "Academic year or curriculum year, or null",
    "category": "Content category (Referensi, Slide, Soal, Catatan, Tugas, Ujian, Praktikum, etc.), or null",
    "additional_context": {"key": "value"}
}

Rules:
- Infer fields from the folder path structure. Do NOT guess if the information is not present.
- The folder path represents breadcrumbs from root to the file's parent folder.
- If a folder name contains a code pattern like [2019] IF2110, extract both year and course_code.
- The category should reflect the content type: Referensi (references/textbooks), Slide (lecture slides), Soal (exams/quizzes), Catatan (notes), etc.
- additional_context is for anything interesting that doesn't fit the main fields.
- Return null (not empty string) for unknown fields."""


class ClassifyFileTool(OrchestratorTool):
    """Uses the LLM to classify a file's metadata from its folder path.

    The classification is NOT rule-based -- the LLM infers structure from
    the raw folder breadcrumb, adapting to any naming convention.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    @property
    def name(self) -> str:
        return "classify_file"

    @property
    def description(self) -> str:
        return (
            "Classify a file's metadata (major, course code, course name, year, category) "
            "by analysing its file name and folder path context. Uses AI to infer structure -- "
            "not rule-based. Call this for each file before ingesting it."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "Name of the file.",
                },
                "folder_path": {
                    "type": "string",
                    "description": "Slash-separated folder breadcrumb from root to file parent, e.g. 'Informatika/Semester 3/IF2120 - Probabilitas/Referensi'.",
                },
                "mime_type": {
                    "type": "string",
                    "description": "MIME type of the file.",
                },
            },
            "required": ["file_name", "folder_path"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        file_name: str = kwargs["file_name"]
        folder_path: str = kwargs["folder_path"]
        mime_type: str = kwargs.get("mime_type", "unknown")

        user_message = (
            f"File: {file_name}\n"
            f"MIME type: {mime_type}\n"
            f"Folder path: {folder_path}\n\n"
            f"Classify this file's metadata."
        )

        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=500,
            )

            content = response.choices[0].message.content or "{}"
            parsed = _parse_json(content)
            if parsed is None:
                parsed = {}

            classification = FileMetadataClassification(
                folder_path=folder_path,
                major=parsed.get("major"),
                course_code=parsed.get("course_code"),
                course_name=parsed.get("course_name"),
                year=parsed.get("year"),
                category=parsed.get("category"),
                additional_context=parsed.get("additional_context", {}),
            )

            return {
                "status": "classified",
                "file_name": file_name,
                "classification": classification.model_dump(),
            }

        except Exception as e:
            logger.warning("Classification failed for %s: %s", file_name, e)
            return {
                "status": "classification_failed",
                "file_name": file_name,
                "error": str(e)[:200],
                "classification": FileMetadataClassification(
                    folder_path=folder_path,
                ).model_dump(),
            }


# ---------------------------------------------------------------------------
# 3. ingest_file
# ---------------------------------------------------------------------------


class IngestFileTool(OrchestratorTool):
    """Downloads a file, processes it (chunk + embed + KG), and commits.

    Each invocation is an atomic unit -- progress is committed after each file.
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageClient,
        connector: SourceConnector,
        job: IngestionJob,
        llm: LLMProvider,
    ) -> None:
        self._db = db
        self._storage = storage
        self._connector = connector
        self._job = job
        self._llm = llm

    @property
    def name(self) -> str:
        return "ingest_file"

    @property
    def description(self) -> str:
        return (
            "Download a file from Google Drive, extract text, chunk it, generate embeddings, "
            "and extract knowledge graph entities. Commits progress after each file. "
            "Provide the classification metadata obtained from classify_file."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "Google Drive file ID.",
                },
                "file_name": {
                    "type": "string",
                    "description": "Original file name.",
                },
                "mime_type": {
                    "type": "string",
                    "description": "MIME type of the file.",
                },
                "folder_path": {
                    "type": "string",
                    "description": "Slash-separated folder breadcrumb.",
                },
                "classification": {
                    "type": "object",
                    "description": "Metadata classification from classify_file (major, course_code, course_name, year, category, additional_context).",
                },
                "admin_user_id": {
                    "type": "string",
                    "description": "Admin user UUID who owns the ingested document.",
                },
            },
            "required": ["file_id", "file_name", "mime_type", "admin_user_id"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        file_id: str = kwargs["file_id"]
        file_name: str = kwargs["file_name"]
        mime_type: str = kwargs["mime_type"]
        folder_path: str = kwargs.get("folder_path", "")
        classification: dict[str, Any] = kwargs.get("classification", {})
        admin_user_id = uuid.UUID(kwargs["admin_user_id"])

        logger.info("Ingesting file: %s (%s)", file_name, file_id)

        # --- Deduplication guard ---
        # Check whether this Drive file has already been successfully ingested.
        # This prevents the LLM agent from inserting a duplicate Document row if
        # it calls ingest_file twice for the same file_id (e.g. after context pruning).
        from sqlalchemy import select as sa_select

        existing_result = await self._db.execute(
            sa_select(Document.id, Document.metadata_["drive_modified_time"].astext)
            .where(
                Document.source == DocumentSource.GOOGLE_DRIVE,
                Document.is_base_knowledge.is_(True),
                Document.status == DocumentStatus.READY,
                Document.metadata_["drive_file_id"].astext == file_id,
            )
            .limit(1)
        )
        existing_row = existing_result.first()
        if existing_row is not None:
            logger.info(
                "File %s (%s) already ingested as document %s — skipping",
                file_name,
                file_id,
                existing_row[0],
            )
            await self._record_file_event(file_id, file_name, "skipped", folder_path)
            return {
                "status": "skipped",
                "file_name": file_name,
                "reason": "already_ingested",
                "document_id": str(existing_row[0]),
            }

        # Event 1: started
        await self._record_file_event(file_id, file_name, "started", folder_path)

        try:
            # Determine target MIME type for processing
            target_mime = mime_type
            if mime_type == "application/vnd.google-apps.document":
                target_mime = (
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                )

            # Get processor
            processor = get_processor(target_mime)
            if processor is None:
                file_ext = SUPPORTED_MIME_TYPES.get(mime_type, "")
                processor = get_processor(file_ext)
            if processor is None:
                await self._record_file_event(file_id, file_name, "skipped", folder_path)
                return {
                    "status": "skipped",
                    "file_name": file_name,
                    "reason": f"No processor for MIME type {mime_type}",
                }

            # Download from Drive
            file_content, filename = await self._connector.download_file(file_id)

            # Store in Supabase Storage
            doc_id = uuid.uuid4()
            storage_path = f"base_kg/{doc_id}/{filename}"

            await self._storage.upload_file(
                file_path=storage_path,
                file_content=file_content,
                content_type=target_mime,
            )

            # Build enriched metadata
            doc_metadata: dict[str, Any] = {
                "drive_file_id": file_id,
                "original_mime_type": mime_type,
                "folder_path": folder_path,
            }
            if classification:
                doc_metadata["classification"] = classification

            # Create Document record
            document = Document(
                id=doc_id,
                user_id=admin_user_id,
                filename=filename,
                file_type=target_mime,
                file_size=len(file_content),
                storage_path=storage_path,
                status=DocumentStatus.PROCESSING,
                source=DocumentSource.GOOGLE_DRIVE,
                is_base_knowledge=True,
                expires_at=None,
                metadata_=doc_metadata,
            )
            self._db.add(document)
            await self._db.commit()
            await self._db.refresh(document)

            # Extract text + chunk
            processing_result = await processor.process(file_content)

            # Store chunks
            chunks_created: list[DocumentChunk] = []
            for chunk_data in processing_result.chunks:
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_data.chunk_index,
                    content=chunk_data.content,
                    page_number=chunk_data.page_number,
                    token_count=len(chunk_data.content.split()),
                    metadata_=chunk_data.metadata,
                )
                self._db.add(chunk)
                chunks_created.append(chunk)

            await self._db.flush()

            document.status = DocumentStatus.READY
            document.chunk_count = len(processing_result.chunks)
            document.metadata_.update(processing_result.metadata)
            document.processed_at = datetime.now(timezone.utc)
            await self._db.commit()

            logger.info(
                "Ingested %s: %d chunks", filename, len(processing_result.chunks)
            )

            # Post-processing: embeddings + KG extraction (non-fatal)
            embed_count = await self._embed_chunks(document, chunks_created)
            kg_stats = await self._extract_knowledge_graph(document, chunks_created)

            # Event 2: completed
            await self._record_file_event(
                file_id, filename, "completed", folder_path,
                extra={"chunks": len(processing_result.chunks), "embeddings": embed_count},
            )

            return {
                "status": "processed",
                "file_name": filename,
                "document_id": str(document.id),
                "chunk_count": len(processing_result.chunks),
                "embeddings_created": embed_count,
                "kg_entities": kg_stats.get("entities_created", 0),
                "kg_relationships": kg_stats.get("relationships_created", 0),
            }

        except Exception as e:
            logger.exception("Failed to ingest file %s: %s", file_name, e)
            await self._record_file_event(file_id, file_name, "failed", folder_path)
            return {
                "status": "failed",
                "file_name": file_name,
                "error": str(e)[:300],
            }

    # -- helpers (ported from IngestionSwarm) --------------------------------

    async def _record_file_event(
        self,
        file_id: str,
        file_name: str,
        state: str,
        folder_path: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Write a file state event (started | completed | skipped | failed) to job metadata_.

        Keyed by file_id so each file gets exactly one entry that gets updated in-place.
        Uses flag_modified + direct SQL UPDATE for JSONB to ensure persistence with pgbouncer.
        """
        try:
            from sqlalchemy.orm.attributes import flag_modified

            file_events: dict = self._job.metadata_.get("file_events", {})
            entry: dict[str, Any] = file_events.get(file_id, {"name": file_name})
            entry["state"] = state
            entry["ts"] = datetime.now(timezone.utc).isoformat()
            if folder_path:
                entry["folder"] = folder_path
            if extra:
                entry.update(extra)
            file_events[file_id] = entry

            # Merge back and flag as modified (required for JSONB in-place mutation)
            new_metadata = dict(self._job.metadata_)
            new_metadata["file_events"] = file_events
            self._job.metadata_ = new_metadata
            flag_modified(self._job, "metadata_")

            # Use SQLAlchemy update() to guarantee the write persists
            from sqlalchemy import update as sa_update

            stmt = (
                sa_update(IngestionJob)
                .where(IngestionJob.id == self._job.id)
                .values(metadata_=new_metadata)
                .execution_options(synchronize_session=False)
            )
            await self._db.execute(stmt)
            await self._db.commit()
        except Exception as e:
            logger.warning("Failed to record file event for %s: %s", file_id, e)

    async def _embed_chunks(
        self,
        document: Document,
        chunks: list[DocumentChunk],
    ) -> int:
        """Generate and store vector embeddings. Non-fatal on failure."""
        if not chunks:
            return 0
        try:
            from app.domain.knowledge.vector_service import VectorService

            vector_service = VectorService(db=self._db)
            chunk_dicts = [
                {"id": c.id, "content": c.content, "metadata": c.metadata_ or {}}
                for c in chunks
            ]
            count = await vector_service.embed_chunks(
                chunks=chunk_dicts, document_id=document.id
            )
            await self._db.commit()
            logger.info("Embedded %d chunks for %s", count, document.id)
            return count
        except Exception as e:
            logger.error(
                "Embedding failed for %s (non-fatal): %s", document.id, e
            )
            return 0

    async def _extract_knowledge_graph(
        self,
        document: Document,
        chunks: list[DocumentChunk],
    ) -> dict[str, int]:
        """Extract entities + relationships into KG. Non-fatal on failure."""
        if not chunks:
            return {"entities_created": 0, "relationships_created": 0}
        try:
            from app.domain.knowledge.kg_builder import KGBuilder
            from app.domain.knowledge.graph_service import GraphService
            from app.infra.neo4j_client import neo4j_client

            graph_service = GraphService(db=self._db, neo4j=neo4j_client)
            kg_builder = KGBuilder(graph_service=graph_service, llm=self._llm)

            chunk_dicts = [
                {"content": c.content, "metadata": c.metadata_ or {}}
                for c in chunks
            ]
            result = await kg_builder.build_from_chunks(
                chunks=chunk_dicts, document_id=document.id
            )
            await self._db.commit()
            logger.info(
                "KG extraction for %s: %d entities, %d rels",
                document.id,
                result.get("entities_created", 0),
                result.get("relationships_created", 0),
            )
            return result
        except Exception as e:
            logger.error(
                "KG extraction failed for %s (non-fatal): %s", document.id, e
            )
            return {"entities_created": 0, "relationships_created": 0}


# ---------------------------------------------------------------------------
# 4. batch_ingest_files  (parallel fan-out of ingest_file)
# ---------------------------------------------------------------------------


class BatchIngestFilesTool(OrchestratorTool):
    """Fan-out ingestion for a batch of files using asyncio.gather.

    Wraps :class:`IngestFileTool` to allow the orchestrator to ingest
    multiple files in parallel rather than sequentially.  Concurrency
    is bounded by ``FILE_CONCURRENCY`` (default 3) from settings, so the
    database and LLM APIs are not overwhelmed.

    The agent should use this instead of calling ``ingest_file`` in a loop
    when it has a list of files ready to process (e.g. all files in a folder
    after calling classify_file for each).
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageClient,
        connector: SourceConnector,
        job: IngestionJob,
        llm: LLMProvider,
        file_concurrency: int = 3,
    ) -> None:
        self._db = db
        self._storage = storage
        self._connector = connector
        self._job = job
        self._semaphore = asyncio.Semaphore(file_concurrency)
        self._ingest_tool = IngestFileTool(
            db=db, storage=storage, connector=connector, job=job, llm=llm
        )

    @property
    def name(self) -> str:
        return "batch_ingest_files"

    @property
    def description(self) -> str:
        return (
            "Ingest multiple files in parallel. Accepts a list of file objects, each "
            "with file_id, file_name, mime_type, folder_path, and classification. "
            "Processes up to FILE_CONCURRENCY files simultaneously. "
            "Use this instead of calling ingest_file in a loop when you have several "
            "files ready to process from the same folder -- it's much faster."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "description": "List of files to ingest in parallel.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_id": {"type": "string", "description": "Google Drive file ID."},
                            "file_name": {"type": "string", "description": "Original file name."},
                            "mime_type": {"type": "string", "description": "MIME type."},
                            "folder_path": {"type": "string", "description": "Slash-separated folder breadcrumb."},
                            "classification": {"type": "object", "description": "Metadata from classify_file."},
                        },
                        "required": ["file_id", "file_name", "mime_type"],
                    },
                },
                "admin_user_id": {
                    "type": "string",
                    "description": "Admin user UUID who owns the ingested documents.",
                },
            },
            "required": ["files", "admin_user_id"],
        }

    async def _ingest_one(self, file_info: dict[str, Any], admin_user_id: str) -> dict[str, Any]:
        """Ingest a single file, bounded by the semaphore."""
        async with self._semaphore:
            return await self._ingest_tool.execute(
                file_id=file_info["file_id"],
                file_name=file_info["file_name"],
                mime_type=file_info["mime_type"],
                folder_path=file_info.get("folder_path", ""),
                classification=file_info.get("classification", {}),
                admin_user_id=admin_user_id,
            )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        files: list[dict[str, Any]] = kwargs["files"]
        admin_user_id: str = kwargs["admin_user_id"]

        if not files:
            return {
                "status": "completed",
                "total": 0,
                "processed": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
            }

        logger.info(
            "BatchIngestFiles: starting %d files (concurrency=%d)",
            len(files),
            self._semaphore._value,  # type: ignore[attr-defined]
        )

        # Fan out all files concurrently, bounded by semaphore
        tasks = [self._ingest_one(f, admin_user_id) for f in files]
        results: list[dict[str, Any]] = await asyncio.gather(*tasks, return_exceptions=False)

        # Tally outcomes
        processed = sum(1 for r in results if r.get("status") == "processed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        skipped = sum(1 for r in results if r.get("status") == "skipped")

        logger.info(
            "BatchIngestFiles complete: %d processed, %d failed, %d skipped",
            processed, failed, skipped,
        )

        return {
            "status": "completed",
            "total": len(files),
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "results": [
                {
                    "file_name": r.get("file_name", ""),
                    "status": r.get("status", "unknown"),
                    "chunk_count": r.get("chunk_count", 0),
                    "error": r.get("error", ""),
                }
                for r in results
            ],
        }


# ---------------------------------------------------------------------------
# 5. update_progress
# ---------------------------------------------------------------------------


class UpdateProgressTool(OrchestratorTool):
    """Persists current progress counts on the IngestionJob row.

    The orchestrator calls this periodically so the admin UI can poll
    for up-to-date stats even while ingestion is still running.
    """

    def __init__(self, db: AsyncSession, job: IngestionJob) -> None:
        self._db = db
        self._job = job

    @property
    def name(self) -> str:
        return "update_progress"

    @property
    def description(self) -> str:
        return (
            "Update the ingestion job's progress counters in the database. "
            "Call this after each file is processed (or after batches) so the admin "
            "can see live progress."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "total_discovered": {
                    "type": "integer",
                    "description": "Total number of ingestible files discovered so far.",
                },
                "files_processed": {
                    "type": "integer",
                    "description": "Files successfully ingested.",
                },
                "files_failed": {
                    "type": "integer",
                    "description": "Files that failed during ingestion.",
                },
                "files_skipped": {
                    "type": "integer",
                    "description": "Files skipped (unsupported type, already ingested, etc.).",
                },
                "message": {
                    "type": "string",
                    "description": "Short status message for logging, e.g. 'Processing Semester 3 folder'.",
                },
                "current_folder": {
                    "type": "string",
                    "description": "The folder currently being processed, e.g. 'Informatika/Semester 3/IF2120 - Probabilitas/Referensi'.",
                },
            },
            "required": ["total_discovered", "files_processed"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from datetime import datetime, timezone
        from sqlalchemy.orm.attributes import flag_modified

        total_discovered: int = kwargs["total_discovered"]
        files_processed: int = kwargs["files_processed"]
        files_failed: int = kwargs.get("files_failed", 0)
        files_skipped: int = kwargs.get("files_skipped", 0)
        message: str = kwargs.get("message", "")
        current_folder: str = kwargs.get("current_folder", "")

        # Determine new status
        new_status = self._job.status
        if self._job.status in (IngestionStatus.PENDING, IngestionStatus.SCANNING):
            new_status = IngestionStatus.PROCESSING

        # Build updated metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        new_metadata = dict(self._job.metadata_)
        if message:
            new_metadata["current_action"] = message
        if current_folder:
            new_metadata["current_folder"] = current_folder

        log_entry: dict[str, Any] = {
            "ts": now_iso,
            "msg": message or f"Progress: {files_processed}/{total_discovered} processed",
            "processed": files_processed,
            "failed": files_failed,
            "skipped": files_skipped,
            "total": total_discovered,
        }
        if current_folder:
            log_entry["folder"] = current_folder
        agent_log: list = new_metadata.get("agent_log", [])
        agent_log.append(log_entry)
        new_metadata["agent_log"] = agent_log[-50:]

        # Update ORM objects
        self._job.total_files = total_discovered
        self._job.processed_files = files_processed
        self._job.failed_files = files_failed
        self._job.skipped_files = files_skipped
        self._job.status = new_status
        self._job.metadata_ = new_metadata
        try:
            flag_modified(self._job, "metadata_")
        except Exception:
            pass  # not an ORM instance (e.g. in tests)

        # Direct SQL UPDATE guarantees persistence with pgbouncer transaction-mode pooling
        from sqlalchemy import update as sa_update

        stmt = (
            sa_update(IngestionJob)
            .where(IngestionJob.id == self._job.id)
            .values(
                status=new_status,
                total_files=total_discovered,
                processed_files=files_processed,
                failed_files=files_failed,
                skipped_files=files_skipped,
                metadata_=new_metadata,
            )
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()

        logger.info(
            "Progress updated (job %s): %d/%d processed, %d failed, %d skipped. %s",
            self._job.id,
            files_processed,
            total_discovered,
            files_failed,
            files_skipped,
            message,
        )

        return {
            "status": "updated",
            "total_discovered": total_discovered,
            "files_processed": files_processed,
            "files_failed": files_failed,
            "files_skipped": files_skipped,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    if "```" in text:
        try:
            start = text.index("```") + 3
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end])
        except json.JSONDecodeError:
            pass

    return None
