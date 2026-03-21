"""PDF document processor — child-process-isolated extraction.

The entire PDF text extraction pipeline (qpdf split + pdftotext) runs in
a **separate Python child process** (`_pdf_worker.py`).  When the child
exits, the OS reclaims ALL its memory — including CPython arena
fragmentation from multi-GB text buffers.  The parent (Celery worker)
only reads the final JSON result and stays lightweight (~350 MB).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app.domain.documents.schemas import ProcessingResult

from .base import BaseProcessor

logger = logging.getLogger(__name__)

# Path to the child worker script (same directory as this file)
_WORKER_SCRIPT = str(Path(__file__).with_name("_pdf_worker.py"))

# Maximum time (seconds) for the entire child process to finish.
# 462-page PDFs with qpdf batching take ~2-3 min; give generous headroom.
_CHILD_TIMEOUT = 600  # 10 minutes

# Maximum extracted text size (characters) to load into the parent process.
# The child worker also enforces this limit, but we double-check here.
# 200K chars ≈ 50-70 pages of dense text — safe for chunking + embedding.
_MAX_TEXT_CHARS = 200_000


class PdfProcessor(BaseProcessor):
    """Process PDF files by spawning an isolated child Python process."""

    @property
    def supported_types(self) -> list[str]:
        return ["application/pdf", "pdf", ".pdf"]

    def _run_worker(self, file_content: bytes) -> dict:
        """Spawn the child worker and return the parsed JSON result.

        Raises on timeout or non-zero exit. Returns the parsed dict on success.
        """
        tmp_pdf = None
        result_file = None
        try:
            # Write PDF bytes to a temp file
            fd, tmp_pdf = tempfile.mkstemp(suffix=".pdf")
            os.write(fd, file_content)
            os.close(fd)

            # Prepare a temp file for the child to write its JSON result
            fd2, result_file = tempfile.mkstemp(suffix=".json")
            os.close(fd2)

            logger.info(
                "PDF processor: spawning child process for %s (%s)",
                tmp_pdf,
                _format_size(os.path.getsize(tmp_pdf)),
            )
            proc = subprocess.run(
                [sys.executable, _WORKER_SCRIPT, tmp_pdf, result_file],
                capture_output=True,
                timeout=_CHILD_TIMEOUT,
            )

            if proc.returncode != 0:
                stderr = proc.stderr.decode(errors="replace")[:2000]
                raise RuntimeError(f"PDF extraction failed (rc={proc.returncode}): {stderr[:500]}")

            with open(result_file) as f:
                data = json.load(f)

            # Truncate text immediately to prevent OOM in the parent process.
            # Large PDFs (500+ pages) can produce multi-MB text strings that
            # explode memory during chunking and embedding.
            text = data.get("text", "")
            if len(text) > _MAX_TEXT_CHARS:
                logger.warning(
                    "PDF text truncated from %d to %d chars (%d pages)",
                    len(text),
                    _MAX_TEXT_CHARS,
                    data.get("page_count", 0),
                )
                data["text"] = text[:_MAX_TEXT_CHARS]
                del text  # free the original large string

            return data
        finally:
            for path in (tmp_pdf, result_file):
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    async def extract_text(self, file_content: bytes) -> str:
        """Extract raw text from a PDF via child process."""
        try:
            data = await asyncio.to_thread(self._run_worker, file_content)
            return data.get("text", "")
        except Exception as exc:
            logger.exception("PDF text extraction failed: %s", exc)
            return ""

    async def process(
        self,
        file_content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> ProcessingResult:
        """Extract text from a PDF in a memory-isolated child process."""
        try:
            data = await asyncio.to_thread(self._run_worker, file_content)

            text = data.get("text", "")
            page_count = data.get("page_count", 0)
            title = data.get("title", "")
            author = data.get("author", "")

            if not text.strip():
                logger.warning("PDF child process produced empty text")
                return ProcessingResult(
                    chunks=[],
                    metadata={"page_count": page_count},
                    page_count=page_count,
                )

            chunks = self._split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            metadata: dict = {"page_count": page_count}
            if title:
                metadata["title"] = title
            if author:
                metadata["author"] = author

            logger.info(
                "PDF processed: %d pages, %d chars, %d chunks",
                page_count,
                len(text),
                len(chunks),
            )
            return ProcessingResult(
                chunks=chunks,
                metadata=metadata,
                page_count=page_count,
                total_characters=len(text),
            )

        except subprocess.TimeoutExpired:
            logger.error("PDF child process timed out after %ds", _CHILD_TIMEOUT)
            return ProcessingResult(
                chunks=[],
                metadata={"error": f"PDF extraction timed out after {_CHILD_TIMEOUT}s"},
            )
        except Exception as exc:
            logger.exception("PDF processing failed: %s", exc)
            return ProcessingResult(
                chunks=[],
                metadata={"error": str(exc)[:500]},
            )


def _format_size(size_bytes: int | float) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
