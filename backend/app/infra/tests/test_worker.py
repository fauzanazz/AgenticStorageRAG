"""Tests for the worker compatibility shim.

The custom poll-loop worker has been replaced by Celery. This file tests
that the shim module exports the expected constants and no-op functions
so existing imports don't break.
"""

from __future__ import annotations


class TestWorkerShim:
    def test_queue_constants_exist(self) -> None:
        """Queue name constants must still be importable for backward compatibility."""
        from app.infra.worker import (
            ALL_QUEUES,
            QUEUE_DOCUMENTS,
            QUEUE_INGESTION,
            QUEUE_KNOWLEDGE,
        )

        assert QUEUE_DOCUMENTS == "jobs:documents"
        assert QUEUE_INGESTION == "jobs:ingestion"
        assert QUEUE_KNOWLEDGE == "jobs:knowledge"
        assert set(ALL_QUEUES) == {QUEUE_DOCUMENTS, QUEUE_INGESTION, QUEUE_KNOWLEDGE}

    def test_register_handler_is_noop(self) -> None:
        """register_handler() must be a no-op (handlers now live in tasks.py)."""
        from app.infra.worker import register_handler

        # Must not raise and must return None
        result = register_handler("some_type", lambda x: x)
        assert result is None
