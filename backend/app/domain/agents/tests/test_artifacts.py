"""Tests for artifact model, service methods, and generate_document tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.agents.tools.generate_document import GenerateDocumentTool


class TestGenerateDocumentTool:
    """Tests for the document generation tool."""

    def test_name(self) -> None:
        tool = GenerateDocumentTool(llm=MagicMock())
        assert tool.name == "generate_document"

    def test_description_not_empty(self) -> None:
        tool = GenerateDocumentTool(llm=MagicMock())
        assert len(tool.description) > 20

    def test_parameters_schema_has_required_fields(self) -> None:
        tool = GenerateDocumentTool(llm=MagicMock())
        schema = tool.parameters_schema
        assert "title" in schema["properties"]
        assert "instructions" in schema["properties"]
        assert "context" in schema["properties"]
        assert "title" in schema["required"]
        assert "instructions" in schema["required"]

    @pytest.mark.asyncio
    async def test_execute_no_instructions_returns_error(self) -> None:
        tool = GenerateDocumentTool(llm=MagicMock())
        result = await tool.execute(title="Test", instructions="")
        assert result["count"] == 0
        assert "error" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_streams_artifact_events(self) -> None:
        """Verify emit_event is called with artifact_start, artifact_delta, artifact_end."""
        # Mock LLM streaming
        mock_llm = AsyncMock()

        # Simulate streaming chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "# Report\n"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = "Some content here."

        async def mock_stream(*args, **kwargs):
            for c in [chunk1, chunk2]:
                yield c

        mock_llm.complete.return_value = mock_stream()

        # Track emitted events
        emitted_events: list[tuple[str, str]] = []

        def emit_event(event_type: str, data_json: str) -> None:
            emitted_events.append((event_type, data_json))

        tool = GenerateDocumentTool(llm=mock_llm)
        result = await tool.execute(
            emit_event=emit_event,
            title="Test Report",
            instructions="Write a test report",
        )

        # Verify result
        assert result["count"] == 1
        assert result["source"] == "generate_document"
        assert result["result"]["title"] == "Test Report"
        assert "# Report\nSome content here." in result["result"]["content"]

        # Verify emitted events
        event_types = [e[0] for e in emitted_events]
        assert event_types[0] == "artifact_start"
        assert "artifact_delta" in event_types
        assert event_types[-1] == "artifact_end"

        # Verify artifact_start payload
        start_data = json.loads(emitted_events[0][1])
        assert start_data["title"] == "Test Report"
        assert start_data["type"] == "markdown"
        assert "artifact_id" in start_data

        # Verify artifact_end payload
        end_data = json.loads(emitted_events[-1][1])
        assert end_data["content_length"] > 0

    @pytest.mark.asyncio
    async def test_execute_without_emit_event(self) -> None:
        """Tool works even without emit_event callback."""
        mock_llm = AsyncMock()

        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Content"

        async def mock_stream(*args, **kwargs):
            yield chunk

        mock_llm.complete.return_value = mock_stream()

        tool = GenerateDocumentTool(llm=mock_llm)
        result = await tool.execute(
            title="No Callback",
            instructions="Write something",
        )

        assert result["count"] == 1
        assert result["result"]["content"] == "Content"

    @pytest.mark.asyncio
    async def test_execute_with_context(self) -> None:
        """Context is passed to the LLM prompt."""
        mock_llm = AsyncMock()

        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Done"

        async def mock_stream(*args, **kwargs):
            yield chunk

        mock_llm.complete.return_value = mock_stream()

        tool = GenerateDocumentTool(llm=mock_llm)
        await tool.execute(
            title="With Context",
            instructions="Summarize",
            context="Entity: John, Role: Engineer",
        )

        # Verify the LLM was called with context in the prompt
        call_args = mock_llm.complete.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Entity: John, Role: Engineer" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_execute_llm_failure_emits_error(self) -> None:
        """When LLM fails, artifact_end includes error."""
        mock_llm = AsyncMock()

        async def mock_stream(*args, **kwargs):
            raise RuntimeError("LLM connection failed")

        mock_llm.complete.return_value = mock_stream()

        emitted: list[tuple[str, str]] = []

        def emit(t: str, d: str) -> None:
            emitted.append((t, d))

        tool = GenerateDocumentTool(llm=mock_llm)
        result = await tool.execute(
            emit_event=emit,
            title="Fail",
            instructions="This will fail",
        )

        assert result["count"] == 0
        assert "error" in result["result"]
