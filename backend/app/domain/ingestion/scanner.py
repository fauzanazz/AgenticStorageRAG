"""Phase 1: Deterministic BFS scanner for Google Drive folders.

Recursively scans ALL folders using a queue (no LLM for traversal),
classifies files per-folder via LLM, and inserts rows into indexed_files.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import Document, DocumentSource, DocumentStatus
from app.domain.ingestion.drive_connector import SUPPORTED_MIME_TYPES
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.models import (
    IndexedFileStatus,
    IngestionJob,
    IngestionStatus,
)
from app.domain.ingestion.orchestrator_tools import CLASSIFY_SYSTEM_PROMPT, _parse_json
from app.domain.ingestion.schemas import DriveFolderEntry
from app.infra.llm import LLMProvider

logger = logging.getLogger(__name__)

# MIME types to skip entirely (not ingestible)
_SKIP_MIME = {"application/vnd.google-apps.shortcut"}


class DriveScanner:
    """Deterministic BFS scanner that indexes all files in a Drive folder tree."""

    def __init__(
        self,
        db: AsyncSession,
        connector: SourceConnector,
        llm: LLMProvider,
        job: IngestionJob,
    ) -> None:
        self._db = db
        self._connector = connector
        self._llm = llm
        self._job = job

    async def scan(
        self,
        root_folder_id: str,
        force: bool = False,
        is_cancelled: Any = None,
    ) -> int:
        """BFS scan of all folders under root_folder_id.

        Args:
            root_folder_id: Google Drive folder ID to start from.
            force: If True, don't skip already-ingested files.
            is_cancelled: Async callable returning True if job was cancelled.

        Returns:
            Total number of files indexed.
        """
        return await self.scan_seeds(
            seeds=[(root_folder_id, "")],
            force=force,
            is_cancelled=is_cancelled,
        )

    async def scan_seeds(
        self,
        seeds: list[tuple[str, str]],
        force: bool = False,
        is_cancelled: Any = None,
    ) -> int:
        """BFS scan starting from multiple seed folders.

        Args:
            seeds: List of (folder_id, path) tuples to BFS from.
            force: If True, don't skip already-ingested files.
            is_cancelled: Async callable returning True if job was cancelled.

        Returns:
            Total number of files indexed.
        """
        queue: deque[tuple[str, str]] = deque(seeds)
        total_indexed = 0

        while queue:
            folder_id, parent_path = queue.popleft()

            # Check cancellation before each folder
            if is_cancelled and await is_cancelled():
                logger.info("Scanner cancelled at folder %s", folder_id)
                return total_indexed

            try:
                entries: list[DriveFolderEntry] = await self._connector.list_folder_children(
                    folder_id
                )
            except Exception as e:
                logger.error(
                    "Failed to scan folder %s (%s): %s — skipping",
                    folder_id,
                    parent_path,
                    e,
                )
                continue

            folders: list[tuple[str, str]] = []
            files: list[DriveFolderEntry] = []

            for entry in entries:
                if entry.is_folder:
                    child_path = f"{parent_path}/{entry.name}" if parent_path else entry.name
                    # Use resolved target for shortcuts pointing to folders
                    recurse_id = entry.target_id or entry.file_id
                    folders.append((recurse_id, child_path))
                elif entry.mime_type in _SKIP_MIME:
                    continue
                elif entry.mime_type in SUPPORTED_MIME_TYPES:
                    files.append(entry)
                # else: unsupported mime, skip silently

            # Enqueue subfolders
            for child_folder_id, child_path in folders:
                queue.append((child_folder_id, child_path))

            if not files:
                logger.info(
                    "Scanned folder %s (%s): 0 ingestible files, %d subfolders",
                    folder_id,
                    parent_path or "(root)",
                    len(folders),
                )
                continue

            # Classify all files in this folder via LLM (one call per folder)
            classifications = await self._classify_folder_files(
                files,
                parent_path,
            )

            # Dedup check: if not force, check which files are already ingested
            skip_file_ids: set[str] = set()
            if not force:
                skip_file_ids = await self._find_already_ingested([f.file_id for f in files])

            # Insert into indexed_files
            count = await self._insert_indexed_files(
                files,
                parent_path,
                classifications,
                skip_file_ids,
            )
            total_indexed += count

            # Update job total_files counter atomically
            await self._increment_total_files(count)
            # Track skipped files atomically
            skipped_count = sum(1 for f in files if f.file_id in skip_file_ids)
            if skipped_count:
                await self._increment_skipped_files(skipped_count)

            logger.info(
                "Scanned folder %s (%s): %d files indexed (%d skipped), %d subfolders",
                folder_id,
                parent_path or "(root)",
                count,
                len(skip_file_ids),
                len(folders),
            )

        return total_indexed

    async def _classify_folder_files(
        self,
        files: list[DriveFolderEntry],
        folder_path: str,
    ) -> dict[str, dict[str, Any]]:
        """Classify all files in a folder with a single LLM call.

        Returns a dict mapping file_id -> classification dict.
        """
        file_list = "\n".join(f"- {f.name} (MIME: {f.mime_type}, ID: {f.file_id})" for f in files)
        user_message = (
            f"Folder path: {folder_path or '(root)'}\n\n"
            f"Classify ALL of these files. Return a JSON array where each element has "
            f'"file_id" and the classification fields.\n\n'
            f"Files:\n{file_list}"
        )

        try:
            response = await self._llm.complete_for_ingestion(
                messages=[
                    {
                        "role": "system",
                        "content": CLASSIFY_SYSTEM_PROMPT
                        + '\n\nWhen given multiple files, return a JSON array of objects. Each object MUST include a "file_id" field matching the provided ID, plus the classification fields (major, course_code, course_name, year, category, additional_context).',
                    },
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=2000,
            )

            content = response.choices[0].message.content or "[]"
            parsed = _parse_json(content)

            # Handle both array and single-object responses
            if isinstance(parsed, list):
                return {
                    item.get("file_id", ""): {k: v for k, v in item.items() if k != "file_id"}
                    for item in parsed
                    if isinstance(item, dict) and item.get("file_id")
                }
            elif isinstance(parsed, dict):
                # Single file or has file_id
                if "file_id" in parsed:
                    fid = parsed["file_id"]
                    return {fid: {k: v for k, v in parsed.items() if k != "file_id"}}
                # Apply same classification to all files
                return {f.file_id: parsed for f in files}

        except Exception as e:
            logger.warning(
                "Classification failed for folder %s: %s — using empty classification",
                folder_path,
                e,
            )

        # Fallback: empty classification for all files
        return {f.file_id: {} for f in files}

    async def _find_already_ingested(
        self,
        file_ids: list[str],
    ) -> set[str]:
        """Find which Drive file IDs already have READY documents."""
        from sqlalchemy import or_ as sa_or

        if not file_ids:
            return set()

        result = await self._db.execute(
            select(Document.metadata_["drive_file_id"].astext).where(
                Document.source == DocumentSource.GOOGLE_DRIVE,
                Document.is_base_knowledge.is_(True),
                sa_or(
                    Document.status == DocumentStatus.READY,
                    Document.status == DocumentStatus.PROCESSING,
                ),
                Document.metadata_["drive_file_id"].astext.in_(file_ids),
            )
        )
        return set(result.scalars().all())

    async def _insert_indexed_files(
        self,
        files: list[DriveFolderEntry],
        folder_path: str,
        classifications: dict[str, dict[str, Any]],
        skip_file_ids: set[str],
    ) -> int:
        """Batch INSERT files into indexed_files. Returns count of rows inserted."""
        if not files:
            return 0

        rows = []
        for f in files:
            is_skipped = f.file_id in skip_file_ids
            status = (
                IndexedFileStatus.SKIPPED.value if is_skipped else IndexedFileStatus.PENDING.value
            )
            stage = "skipped" if is_skipped else "pending"
            classification = classifications.get(f.file_id, {})
            rows.append(
                {
                    "job_id": str(self._job.id),
                    "drive_file_id": f.file_id,
                    "file_name": f.name,
                    "mime_type": f.mime_type,
                    "size_bytes": f.size,
                    "folder_path": folder_path,
                    "classification": json.dumps(classification),
                    "status": status,
                    "stage": stage,
                }
            )

        # Batch insert with ON CONFLICT DO NOTHING for idempotency
        placeholders = []
        params: dict[str, Any] = {}
        for i, row in enumerate(rows):
            cols = ", ".join(f":{k}_{i}" for k in row)
            placeholders.append(f"({cols})")
            for k, v in row.items():
                params[f"{k}_{i}"] = v

        columns = "job_id, drive_file_id, file_name, mime_type, size_bytes, folder_path, classification, status, stage"
        stmt = text(
            f"INSERT INTO indexed_files ({columns}) "
            f"VALUES {', '.join(placeholders)} "
            f"ON CONFLICT (job_id, drive_file_id) DO NOTHING"
        )
        result = await self._db.execute(stmt, params)
        await self._db.commit()
        return result.rowcount or 0

    async def _increment_total_files(self, delta: int) -> None:
        """Atomically increment the job's total_files counter."""
        from sqlalchemy import update as sa_update

        stmt = (
            sa_update(IngestionJob)
            .where(
                IngestionJob.id == self._job.id,
                IngestionJob.status != IngestionStatus.CANCELLED,
            )
            .values(total_files=IngestionJob.total_files + delta)
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def _increment_skipped_files(self, delta: int) -> None:
        """Atomically increment the job's skipped_files counter."""
        from sqlalchemy import update as sa_update

        stmt = (
            sa_update(IngestionJob)
            .where(
                IngestionJob.id == self._job.id,
                IngestionJob.status != IngestionStatus.CANCELLED,
            )
            .values(skipped_files=IngestionJob.skipped_files + delta)
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()
