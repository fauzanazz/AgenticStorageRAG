"""Fetch full document tool for the RAG agent.

Retrieves the complete text content of a document from Google Drive or
Supabase Storage and injects it into the LLM context.  When the extracted
text exceeds MAX_FULL_TEXT_CHARS it falls back to chunk-based retrieval
(5 chunks at a time, ranked by vector similarity).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agents.interfaces import EventEmitter, IAgentTool
from app.domain.documents.models import Document, DocumentChunk, DocumentSource, DocumentStatus
from app.domain.documents.processors import get_processor
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

# If the full extracted text exceeds this threshold we switch to chunk
# retrieval instead of injecting the entire document.
MAX_FULL_TEXT_CHARS = 100_000

# Number of chunks returned per page in fallback mode.
CHUNKS_PER_PAGE = 5


class FetchDocumentTool(IAgentTool):
    """Fetch the full text of a document for the LLM to reason over.

    The agent uses this when the user explicitly asks to read, view, or
    retrieve an entire document rather than relying on RAG chunks.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "fetch_document"

    @property
    def description(self) -> str:
        return (
            "Fetch the FULL text content of a specific document so you can "
            "read and reason over the entire file. Use this when the user "
            "explicitly asks to see, read, or retrieve a complete document "
            "(e.g. 'show me the full report', 'read the entire file'). "
            "Requires a document_id from prior search results or citations. "
            "For very large documents the tool automatically falls back to "
            "returning the most relevant chunks — you can request more by "
            "increasing chunk_offset. "
            "Input: document_id (UUID str, required), "
            "query (str, optional — for ranking chunks on large docs), "
            "chunk_offset (int, default 0 — pagination for large docs)"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "UUID of the document to fetch.",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "The user's query. Used to rank chunks by relevance "
                        "when the document is too large for full retrieval."
                    ),
                },
                "chunk_offset": {
                    "type": "integer",
                    "description": (
                        "Offset for paginated chunk retrieval on large "
                        "documents (default 0). Each page returns 5 chunks."
                    ),
                },
            },
            "required": ["document_id"],
        }

    async def execute(
        self, emit_event: EventEmitter = None, **kwargs: Any
    ) -> dict[str, Any]:
        document_id_str: str = kwargs.get("document_id", "")
        chunk_offset: int = kwargs.get("chunk_offset", 0)

        # -- Validate document_id ----------------------------------------
        try:
            doc_id = uuid.UUID(document_id_str)
        except (ValueError, AttributeError):
            return {"result": [], "error": "Invalid document_id", "count": 0}

        # -- Look up the document ----------------------------------------
        result = await self._db.execute(
            select(Document).where(Document.id == doc_id)
        )
        document: Document | None = result.scalar_one_or_none()

        if document is None:
            return {"result": [], "error": "Document not found", "count": 0}

        if document.status != DocumentStatus.READY:
            return {
                "result": [],
                "error": f"Document is not ready (status: {document.status.value})",
                "count": 0,
            }

        # -- Build source URL --------------------------------------------
        source_url = self._build_source_url(document)

        # -- Try to download and extract full text -----------------------
        try:
            file_bytes = await self._download(document)
        except Exception as e:
            logger.warning("Failed to download document %s: %s", doc_id, e)
            # Fall back to chunk retrieval if download fails
            return await self._chunk_fallback(
                doc_id=doc_id,
                document=document,
                offset=chunk_offset,
                source_url=source_url,
                reason=f"Download failed: {e}",
            )

        full_text = await self._extract_text(document, file_bytes)

        if not full_text:
            return {
                "result": {
                    "content": "",
                    "document_name": document.filename,
                    "source_url": source_url,
                    "mode": "full",
                },
                "error": "Could not extract text from this file type",
                "count": 0,
                "source": "fetch_document",
            }

        # -- Size check: full text vs chunk fallback ---------------------
        if len(full_text) <= MAX_FULL_TEXT_CHARS:
            return {
                "result": {
                    "content": full_text,
                    "document_name": document.filename,
                    "source_url": source_url,
                    "mode": "full",
                },
                "count": 1,
                "source": "fetch_document",
            }

        # Document is too large — fall back to chunks
        return await self._chunk_fallback(
            doc_id=doc_id,
            document=document,
            offset=chunk_offset,
            source_url=source_url,
            reason=f"Document too large ({len(full_text):,} chars). Returning relevant chunks instead.",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _download(self, document: Document) -> bytes:
        """Download file bytes from the appropriate source."""
        if document.source == DocumentSource.GOOGLE_DRIVE:
            drive_file_id = (document.metadata_ or {}).get("drive_file_id")
            if not drive_file_id:
                raise ValueError("Document has no drive_file_id in metadata")

            from app.domain.ingestion.drive_connector import GoogleDriveConnector

            connector = GoogleDriveConnector()
            await connector.authenticate()
            content, _ = await connector.download_file(drive_file_id)
            return content

        # User upload — download from Supabase Storage
        if not document.storage_path:
            raise ValueError("Document has no storage_path")

        storage = StorageClient()
        return await storage.download_file(document.storage_path)

    async def _extract_text(
        self, document: Document, file_bytes: bytes
    ) -> str:
        """Extract raw text from file bytes using the processor registry."""
        file_ext = Path(document.filename).suffix.lower().lstrip(".")
        processor = get_processor(document.file_type) or get_processor(file_ext)

        if processor is None:
            logger.warning(
                "No processor for file type %s / ext %s",
                document.file_type,
                file_ext,
            )
            return ""

        return await processor.extract_text(file_bytes)

    async def _chunk_fallback(
        self,
        *,
        doc_id: uuid.UUID,
        document: Document,
        offset: int,
        source_url: str | None,
        reason: str,
    ) -> dict[str, Any]:
        """Return chunks from the DB ordered by chunk_index with pagination."""
        try:
            result = await self._db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc_id)
                .order_by(DocumentChunk.chunk_index)
                .offset(offset)
                .limit(CHUNKS_PER_PAGE)
            )
            chunks = list(result.scalars().all())
        except Exception as e:
            logger.error("Chunk fallback query failed: %s", e)
            return {
                "result": [],
                "error": f"Chunk retrieval failed: {e}",
                "count": 0,
                "source": "fetch_document",
            }

        chunks_content = "\n\n---\n\n".join(c.content for c in chunks)

        return {
            "result": {
                "content": chunks_content,
                "document_name": document.filename,
                "source_url": source_url,
                "mode": "chunks",
                "total_chunks": document.chunk_count,
                "chunk_offset": offset,
                "chunks_returned": len(chunks),
                "fallback_reason": reason,
            },
            "count": len(chunks),
            "source": "fetch_document",
        }

    @staticmethod
    def _build_source_url(document: Document) -> str | None:
        """Build a clickable URL for the document source."""
        if document.source == DocumentSource.GOOGLE_DRIVE:
            drive_file_id = (document.metadata_ or {}).get("drive_file_id")
            if drive_file_id:
                return f"https://drive.google.com/file/d/{drive_file_id}/view"
        return None
