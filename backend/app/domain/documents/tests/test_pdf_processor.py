"""Tests for the PdfProcessor (child-process-isolated architecture)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.domain.documents.processors.pdf import PdfProcessor, _WORKER_SCRIPT
from app.domain.documents.schemas import ProcessingResult


FAKE_PDF = b"%PDF-1.4 fake content"
FAKE_TEXT = "Hello world. " * 200  # enough for at least one chunk


def _make_worker_result(
    text: str = FAKE_TEXT,
    page_count: int = 5,
    title: str = "Test PDF",
    author: str = "Author",
) -> dict:
    return {"text": text, "page_count": page_count, "title": title, "author": author}


def _fake_subprocess_run(worker_result: dict, returncode: int = 0):
    """Return a fake subprocess.run that writes worker_result JSON to output file."""

    def _run(cmd, capture_output=False, timeout=None):
        # cmd = [python, _WORKER_SCRIPT, input_pdf, output_json]
        output_json_path = cmd[3]
        if returncode == 0:
            with open(output_json_path, "w") as f:
                json.dump(worker_result, f)
        mock_proc = MagicMock()
        mock_proc.returncode = returncode
        mock_proc.stderr = b"extraction error" if returncode != 0 else b""
        return mock_proc

    return _run


class TestPdfProcessor:
    """Tests for PdfProcessor."""

    @pytest.fixture
    def processor(self):
        return PdfProcessor()

    @pytest.mark.asyncio
    async def test_process_success(self, processor):
        with patch("subprocess.run", side_effect=_fake_subprocess_run(_make_worker_result())):
            result = await processor.process(FAKE_PDF)

        assert isinstance(result, ProcessingResult)
        assert len(result.chunks) > 0
        assert result.page_count == 5
        assert result.total_characters == len(FAKE_TEXT)
        assert result.metadata["page_count"] == 5
        assert result.metadata["title"] == "Test PDF"
        assert result.metadata["author"] == "Author"

    @pytest.mark.asyncio
    async def test_process_spawns_correct_worker(self, processor):
        """Verify the child process is called with the right script path."""
        captured = {}

        def _capture_run(cmd, **kwargs):
            captured["cmd"] = cmd
            output_json_path = cmd[3]
            with open(output_json_path, "w") as f:
                json.dump(_make_worker_result(), f)
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = b""
            return mock

        with patch("subprocess.run", side_effect=_capture_run):
            await processor.process(FAKE_PDF)

        cmd = captured["cmd"]
        assert cmd[0] == sys.executable, "should use the current Python interpreter"
        assert cmd[1] == _WORKER_SCRIPT, "should call the _pdf_worker.py script"
        assert cmd[2].endswith(".pdf"), "third arg should be temp pdf path"
        assert cmd[3].endswith(".json"), "fourth arg should be temp result json path"

    @pytest.mark.asyncio
    async def test_process_child_failure_returns_empty(self, processor):
        """When child process fails, return empty ProcessingResult."""
        with patch("subprocess.run", side_effect=_fake_subprocess_run({}, returncode=1)):
            result = await processor.process(FAKE_PDF)

        assert result.chunks == []
        assert "error" in result.metadata

    @pytest.mark.asyncio
    async def test_process_timeout_returns_empty(self, processor):
        """When child process times out, return empty ProcessingResult."""

        def _timeout_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout=600)

        with patch("subprocess.run", side_effect=_timeout_run):
            result = await processor.process(FAKE_PDF)

        assert result.chunks == []
        assert "error" in result.metadata
        assert "timed out" in result.metadata["error"].lower()

    @pytest.mark.asyncio
    async def test_process_empty_text_returns_empty(self, processor):
        """When child returns empty text, return ProcessingResult with no chunks."""
        empty_result = _make_worker_result(text="   ", page_count=3)
        with patch("subprocess.run", side_effect=_fake_subprocess_run(empty_result)):
            result = await processor.process(FAKE_PDF)

        assert result.chunks == []
        assert result.page_count == 3

    @pytest.mark.asyncio
    async def test_process_cleanup_temp_files(self, processor):
        """Temp files should be cleaned up after processing."""
        paths_to_check = []

        def _capture_run(cmd, **kwargs):
            paths_to_check.extend([cmd[2], cmd[3]])
            output_json_path = cmd[3]
            with open(output_json_path, "w") as f:
                json.dump(_make_worker_result(), f)
            m = MagicMock()
            m.returncode = 0
            m.stderr = b""
            return m

        with patch("subprocess.run", side_effect=_capture_run):
            await processor.process(FAKE_PDF)

        for p in paths_to_check:
            assert not os.path.exists(p), f"Temp file not cleaned up: {p}"

    @pytest.mark.asyncio
    async def test_process_metadata_title_author(self, processor):
        """Metadata should include title and author from child output."""
        result_data = _make_worker_result(title="My Book", author="Jane Doe")
        with patch("subprocess.run", side_effect=_fake_subprocess_run(result_data)):
            result = await processor.process(FAKE_PDF)

        assert result.metadata.get("title") == "My Book"
        assert result.metadata.get("author") == "Jane Doe"

    @pytest.mark.asyncio
    async def test_process_no_title_skips_metadata(self, processor):
        """When title/author are empty, they should NOT appear in metadata."""
        result_data = _make_worker_result(title="", author="")
        with patch("subprocess.run", side_effect=_fake_subprocess_run(result_data)):
            result = await processor.process(FAKE_PDF)

        assert "title" not in result.metadata
        assert "author" not in result.metadata
        assert result.chunks  # text was extracted

    @pytest.mark.asyncio
    async def test_process_exception_returns_empty(self, processor):
        """Unexpected exceptions are caught and return empty ProcessingResult."""

        def _raise(cmd, **kwargs):
            raise RuntimeError("unexpected failure")

        with patch("subprocess.run", side_effect=_raise):
            result = await processor.process(FAKE_PDF)

        assert result.chunks == []
        assert "error" in result.metadata

    @pytest.mark.asyncio
    async def test_extract_text_success(self, processor):
        """extract_text should return the text from the worker result."""
        with patch("subprocess.run", side_effect=_fake_subprocess_run(_make_worker_result())):
            text = await processor.extract_text(FAKE_PDF)

        assert text == FAKE_TEXT

    @pytest.mark.asyncio
    async def test_extract_text_failure_returns_empty(self, processor):
        """extract_text should return empty string on failure."""

        def _raise(cmd, **kwargs):
            raise RuntimeError("fail")

        with patch("subprocess.run", side_effect=_raise):
            text = await processor.extract_text(FAKE_PDF)

        assert text == ""
