"""
Standalone PDF extraction worker process.

This script runs in a **separate Python process** to isolate memory.
When it exits, ALL memory (including CPython arena fragmentation) is
returned to the OS -- solving the permanent RSS bloat from processing
large PDFs.

Usage:
    python -m app.domain.documents.processors._pdf_worker <pdf_path> <output_json_path>

Output JSON schema:
    {
        "text": "full extracted text...",
        "page_count": 462,
        "title": "Clean Code",
        "author": "Robert C. Martin"
    }
"""

from __future__ import annotations

import gc
import json
import logging
import os
import resource
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BATCH_PAGES = 20
_SUBPROCESS_TIMEOUT = 10  # seconds per qpdf/pdftotext call
_MAX_SUBPROCESS_MEMORY = 512 * 1024 * 1024  # 512 MB RLIMIT_AS


def _limit_memory() -> None:
    """preexec_fn: cap child subprocess virtual address space."""
    try:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (_MAX_SUBPROCESS_MEMORY, _MAX_SUBPROCESS_MEMORY),
        )
    except (ValueError, OSError):
        pass


# ---------------------------------------------------------------------------
# PDF metadata via pdfinfo (Poppler)
# ---------------------------------------------------------------------------
def _extract_pdf_metadata(pdf_path: str) -> tuple[int, str | None, str | None]:
    """Return (page_count, title, author) using pdfinfo."""
    try:
        result = subprocess.run(
            ["pdfinfo", pdf_path],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
            preexec_fn=_limit_memory,
        )
        text = result.stdout.decode("utf-8", errors="replace")
        pages = 0
        title = None
        author = None
        for line in text.splitlines():
            if line.startswith("Pages:"):
                pages = int(line.split(":", 1)[1].strip())
            elif line.startswith("Title:"):
                title = line.split(":", 1)[1].strip() or None
            elif line.startswith("Author:"):
                author = line.split(":", 1)[1].strip() or None
        return pages, title, author
    except Exception:
        return 0, None, None


def _count_pages_pdftotext(pdf_path: str) -> int:
    """Fallback page count via pdftotext (count form-feeds)."""
    try:
        result = subprocess.run(
            ["pdftotext", pdf_path, "-"],
            capture_output=True,
            timeout=30,
            preexec_fn=_limit_memory,
        )
        return result.stdout.count(b"\x0c")
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# qpdf split + pdftotext extraction
# ---------------------------------------------------------------------------
def _qpdf_split_batch(
    src_pdf: str,
    first_page: int,
    last_page: int,
    out_pdf: str,
) -> bool:
    """Split pages [first_page..last_page] into out_pdf via qpdf."""
    try:
        result = subprocess.run(
            [
                "qpdf",
                src_pdf,
                "--pages",
                ".",
                f"{first_page}-{last_page}",
                "--",
                out_pdf,
            ],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
            preexec_fn=_limit_memory,
        )
        return result.returncode in (0, 3)  # 3 = warnings but OK
    except (subprocess.TimeoutExpired, OSError):
        return False


def _pdftotext_extract(pdf_path: str) -> str:
    """Extract text from a (small, split) PDF via pdftotext."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
            preexec_fn=_limit_memory,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError):
        pass
    return ""


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------
def _extract_split_then_text(
    pdf_path: str,
    max_pages: int | None = None,
) -> tuple[str, int, str | None, str | None]:
    """
    Extract text from a PDF using qpdf split + pdftotext.

    Args:
        pdf_path: Path to the PDF file.
        max_pages: If set, only extract the first N pages to limit memory usage.

    Returns (full_text, page_count, title, author).
    """
    page_count, title, author = _extract_pdf_metadata(pdf_path)
    if page_count == 0:
        page_count = _count_pages_pdftotext(pdf_path)
    if page_count == 0:
        return "", 0, None, None

    extract_pages = min(page_count, max_pages) if max_pages else page_count
    total_batches = (extract_pages + _BATCH_PAGES - 1) // _BATCH_PAGES
    text_parts: list[str] = []
    consecutive_failures = 0

    tmp_dir = tempfile.mkdtemp(prefix="pdf_split_")
    try:
        for batch_idx in range(total_batches):
            first = batch_idx * _BATCH_PAGES + 1
            last = min((batch_idx + 1) * _BATCH_PAGES, extract_pages)
            split_pdf = os.path.join(tmp_dir, f"batch_{batch_idx:04d}.pdf")

            ok = _qpdf_split_batch(pdf_path, first, last, split_pdf)
            if ok and os.path.exists(split_pdf):
                batch_text = _pdftotext_extract(split_pdf)
                if batch_text:
                    text_parts.append(batch_text)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                # Remove split file immediately to free disk
                try:
                    os.unlink(split_pdf)
                except OSError:
                    pass
            else:
                consecutive_failures += 1
                if batch_idx == 0:
                    # First batch failed -- try direct pdftotext on first 5 pages
                    try:
                        result = subprocess.run(
                            ["pdftotext", "-f", "1", "-l", "5", pdf_path, "-"],
                            capture_output=True,
                            timeout=_SUBPROCESS_TIMEOUT,
                            preexec_fn=_limit_memory,
                        )
                        if result.returncode == 0 and result.stdout:
                            text_parts.append(
                                result.stdout.decode("utf-8", errors="replace")
                            )
                    except Exception:
                        pass

            # Abort if too many consecutive failures
            if consecutive_failures >= 3:
                break

            # Periodic GC
            if (batch_idx + 1) % 5 == 0:
                gc.collect()
    finally:
        # Cleanup temp dir
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    full_text = "\n".join(text_parts)
    return full_text, page_count, title, author


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    if len(sys.argv) != 3:
        print(
            json.dumps({"error": "Usage: _pdf_worker.py <pdf_path> <output_json_path>"}),
            file=sys.stderr,
        )
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2]

    # Maximum text output — prevents OOM in both child and parent processes.
    _MAX_TEXT_CHARS = 200_000  # ~50-70 pages of dense text
    # Maximum pages to extract — stop the child process early for huge PDFs.
    _MAX_PAGES = 50

    if not os.path.exists(pdf_path):
        result = {"text": "", "page_count": 0, "title": None, "author": None}
    else:
        text, page_count, title, author = _extract_split_then_text(
            pdf_path, max_pages=_MAX_PAGES,
        )
        if len(text) > _MAX_TEXT_CHARS:
            text = text[:_MAX_TEXT_CHARS]
        result = {
            "text": text,
            "page_count": page_count,
            "title": title,
            "author": author,
        }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
