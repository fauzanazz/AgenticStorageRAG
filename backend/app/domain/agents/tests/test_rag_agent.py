"""Tests for the ReAct RAG agent."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.agents.rag_agent import MAX_REACT_ITERATIONS, RAGAgent
from app.domain.agents.schemas import (
    ChatRequest,
    ConversationResponse,
    MessageResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_call_obj(
    name: str = "hybrid_search",
    arguments: str = '{"query": "AI"}',
    call_id: str | None = None,
) -> MagicMock:
    """Return a MagicMock that looks like an OpenAI tool_call object."""
    tc = MagicMock()
    tc.id = call_id or f"call_{uuid.uuid4().hex[:8]}"
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_llm_response(
    content: str | None = None,
    tool_calls: list[MagicMock] | None = None,
) -> MagicMock:
    """Return a MagicMock that looks like a LiteLLM response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls  # None means text-only response
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = msg
    return resp


def _make_stream_chunk(content: str) -> MagicMock:
    """Return a MagicMock streaming chunk."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock()
    chunk.choices[0].delta.content = content
    return chunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_chat_service(now: datetime) -> AsyncMock:
    service = AsyncMock()
    service.create_conversation.return_value = ConversationResponse(
        id=uuid.uuid4(),
        title="New conversation",
        created_at=now,
        updated_at=now,
        message_count=0,
    )
    service.add_message.return_value = MessageResponse(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="user",
        content="test",
        created_at=now,
    )
    service.get_messages.return_value = [
        MessageResponse(
            id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            role="user",
            content="What is AI?",
            created_at=now,
        )
    ]
    return service


@pytest.fixture
def mock_tool() -> MagicMock:
    """A mock tool with the required parameters_schema property."""
    tool = MagicMock()
    tool.name = "hybrid_search"
    tool.description = "Search everything"
    tool.parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    }
    tool.execute = AsyncMock(return_value={
        "result": [
            {
                "content": "AI is artificial intelligence",
                "source": "vector",
                "score": 0.9,
                "document_id": str(uuid.uuid4()),
                "chunk_id": str(uuid.uuid4()),
            }
        ],
        "count": 1,
        "source": "hybrid",
    })
    return tool


@pytest.fixture
def agent(
    mock_llm: AsyncMock,
    mock_chat_service: AsyncMock,
    mock_tool: MagicMock,
) -> RAGAgent:
    return RAGAgent(
        llm=mock_llm,
        chat_service=mock_chat_service,
        tools=[mock_tool],
    )


# ---------------------------------------------------------------------------
# Tests — ReAct loop
# ---------------------------------------------------------------------------


class TestRAGAgentReActLoop:
    """Tests for the native-tool-calling ReAct loop."""

    @pytest.mark.asyncio
    async def test_react_loop_executes_tool_calls(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
        mock_tool: MagicMock,
    ) -> None:
        """LLM returning tool_calls causes the tool to be executed."""
        tc = _make_tool_call_obj("hybrid_search", '{"query": "AI"}')

        # Iteration 1: LLM requests tool call; iteration 2 (synthesis): streaming fails
        mock_llm.complete.side_effect = [
            _make_llm_response(tool_calls=[tc]),   # ReAct iteration 1
            Exception("streaming failed"),          # streaming attempt fails
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "AI is Artificial Intelligence."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="What is AI?", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # Tool must have been called
        mock_tool.execute.assert_awaited_once()
        tool_call_events = [e for e in events if e.event == "tool_call"]
        assert len(tool_call_events) == 1
        tc_data = json.loads(tool_call_events[0].data)
        assert tc_data["tool_name"] == "hybrid_search"

    @pytest.mark.asyncio
    async def test_react_loop_executes_multiple_tools_in_parallel(
        self,
        mock_llm: AsyncMock,
        mock_chat_service: AsyncMock,
    ) -> None:
        """Multiple tool calls in one iteration run with asyncio.gather."""
        tool_a = MagicMock()
        tool_a.name = "graph_search"
        tool_a.description = "Graph search"
        tool_a.parameters_schema = {"type": "object", "properties": {"query": {"type": "string"}}}
        tool_a.execute = AsyncMock(return_value={"result": [], "count": 0, "source": "graph"})

        tool_b = MagicMock()
        tool_b.name = "vector_search"
        tool_b.description = "Vector search"
        tool_b.parameters_schema = {"type": "object", "properties": {"query": {"type": "string"}}}
        tool_b.execute = AsyncMock(return_value={"result": [], "count": 0, "source": "vector"})

        agent = RAGAgent(llm=mock_llm, chat_service=mock_chat_service, tools=[tool_a, tool_b])

        tc_a = _make_tool_call_obj("graph_search", '{"query": "test"}')
        tc_b = _make_tool_call_obj("vector_search", '{"query": "test"}')

        mock_llm.complete.side_effect = [
            _make_llm_response(tool_calls=[tc_a, tc_b]),  # both tools in one iteration
            Exception("streaming failed"),
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "Answer."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # Both tools should have been called
        tool_a.execute.assert_awaited_once()
        tool_b.execute.assert_awaited_once()
        tool_call_events = [e for e in events if e.event == "tool_call"]
        assert len(tool_call_events) == 2

    @pytest.mark.asyncio
    async def test_react_loop_no_tool_calls_uses_fallback(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
        mock_tool: MagicMock,
    ) -> None:
        """If the LLM returns no tool calls, hybrid_search runs as fallback."""
        mock_llm.complete.side_effect = [
            _make_llm_response(content="I don't need tools.", tool_calls=None),
            Exception("streaming failed"),
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "Answer."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # Fallback hybrid_search should have been called
        mock_tool.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_react_loop_stops_after_max_iterations(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
        mock_tool: MagicMock,
    ) -> None:
        """Loop terminates after MAX_REACT_ITERATIONS even if LLM keeps returning tool calls."""
        tc = _make_tool_call_obj("hybrid_search", '{"query": "test"}')

        # Always return tool_calls → loop must stop at MAX_REACT_ITERATIONS
        tool_call_resp = _make_llm_response(tool_calls=[tc])
        mock_llm.complete.side_effect = [tool_call_resp] * (MAX_REACT_ITERATIONS + 10)

        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "Answer after max iterations."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # LLM called exactly MAX_REACT_ITERATIONS times in the loop
        # + 1 for the streaming synthesis attempt (falls back to complete_with_retry)
        assert mock_llm.complete.call_count <= MAX_REACT_ITERATIONS + 1


# ---------------------------------------------------------------------------
# Tests — chat flow
# ---------------------------------------------------------------------------


class TestRAGAgentChat:
    """Tests for the overall chat flow (event emission, conversation management)."""

    @pytest.mark.asyncio
    async def test_chat_creates_conversation(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
        mock_chat_service: AsyncMock,
    ) -> None:
        """When no conversation_id is provided, a new one should be created."""
        mock_llm.complete.side_effect = [
            _make_llm_response(content="No tools needed.", tool_calls=None),
            Exception("streaming failed"),
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "AI stands for Artificial Intelligence."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="What is AI?")
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        event_types = [e.event for e in events]
        assert "conversation_created" in event_types
        assert "done" in event_types
        mock_chat_service.create_conversation.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_uses_existing_conversation(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
        mock_chat_service: AsyncMock,
    ) -> None:
        """When conversation_id is provided, no new conversation is created."""
        mock_llm.complete.side_effect = [
            _make_llm_response(content="Answer.", tool_calls=None),
            Exception("streaming failed"),
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "Answer."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        event_types = [e.event for e in events]
        assert "conversation_created" not in event_types
        assert "done" in event_types
        mock_chat_service.create_conversation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_emits_tokens(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
    ) -> None:
        """Response tokens should be streamed as token events."""
        mock_llm.complete.side_effect = [
            _make_llm_response(content="No tools.", tool_calls=None),
            Exception("streaming fails → fallback"),
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "The answer is simple."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        token_events = []
        async for event in agent.chat(request, uuid.uuid4()):
            if event.event == "token":
                token_events.append(event.data)

        full_response = "".join(token_events)
        assert "answer" in full_response

    @pytest.mark.asyncio
    async def test_chat_handles_error(
        self,
        agent: RAGAgent,
        mock_chat_service: AsyncMock,
    ) -> None:
        """Errors during message save should be caught and emitted as error events."""
        mock_chat_service.add_message.side_effect = Exception("DB error")

        request = ChatRequest(message="test")
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        error_events = [e for e in events if e.event == "error"]
        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_chat_emits_done_event(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
    ) -> None:
        """A done event must always be the final event."""
        mock_llm.complete.side_effect = [
            _make_llm_response(content="No tools.", tool_calls=None),
            Exception("streaming fails"),
        ]
        synthesis = MagicMock()
        synthesis.choices = [MagicMock()]
        synthesis.choices[0].message.content = "Done."
        mock_llm.complete_with_retry.return_value = synthesis

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        assert events[-1].event == "done"

    @pytest.mark.asyncio
    async def test_chat_with_streaming_llm(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
    ) -> None:
        """When the LLM streams correctly, tokens come from the stream."""
        # First complete call → ReAct iteration (no tool_calls → break out of loop)
        react_resp = _make_llm_response(content="No tools needed.", tool_calls=None)

        # Second call (streaming synthesis) → returns an async iterable
        async def _stream():
            for word in ["The ", "answer ", "is ", "42."]:
                yield _make_stream_chunk(word)

        call_count = 0

        async def _complete_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return react_resp
            return _stream()

        mock_llm.complete = AsyncMock(side_effect=_complete_side_effect)

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        token_events = []
        async for event in agent.chat(request, uuid.uuid4()):
            if event.event == "token":
                token_events.append(event.data)

        assert "".join(token_events) == "The answer is 42."
