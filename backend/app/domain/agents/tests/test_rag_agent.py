"""Tests for the ReAct RAG agent."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
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


def _make_stream_chunk(
    content: str | None = None,
    tool_calls: list[MagicMock] | None = None,
) -> MagicMock:
    """Return a MagicMock streaming chunk."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    chunk.choices[0].delta = delta
    return chunk


def _make_tool_call_delta(
    index: int = 0,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> MagicMock:
    """Return a MagicMock tool_call delta for streaming."""
    tc = MagicMock()
    tc.index = index
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


async def _async_iter(items):
    """Helper: wrap a list into an async iterable."""
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


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
    tool.execute = AsyncMock(
        return_value={
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
        }
    )
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
        # Iteration 1: stream returns a tool call
        tc_delta = _make_tool_call_delta(
            index=0, call_id="call_123", name="hybrid_search", arguments='{"query": "AI"}'
        )
        iter1_chunks = [
            _make_stream_chunk(content="Let me search.", tool_calls=None),
            _make_stream_chunk(content=None, tool_calls=[tc_delta]),
        ]
        # Iteration 2: stream returns final answer (no tool calls)
        iter2_chunks = [
            _make_stream_chunk(content="AI is Artificial Intelligence."),
        ]

        call_count = 0

        async def _complete_side(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _async_iter(iter1_chunks)
            return _async_iter(iter2_chunks)

        mock_llm.complete = AsyncMock(side_effect=_complete_side)

        request = ChatRequest(message="What is AI?", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # Tool must have been called
        mock_tool.execute.assert_awaited_once()
        tool_start_events = [e for e in events if e.event == "tool_start"]
        assert len(tool_start_events) == 1
        tc_data = json.loads(tool_start_events[0].data)
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

        tc_a_delta = _make_tool_call_delta(
            index=0, call_id="call_a", name="graph_search", arguments='{"query": "test"}'
        )
        tc_b_delta = _make_tool_call_delta(
            index=1, call_id="call_b", name="vector_search", arguments='{"query": "test"}'
        )

        iter1_chunks = [_make_stream_chunk(content=None, tool_calls=[tc_a_delta, tc_b_delta])]
        iter2_chunks = [_make_stream_chunk(content="Answer.")]

        call_count = 0

        async def _complete_side(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _async_iter(iter1_chunks)
            return _async_iter(iter2_chunks)

        mock_llm.complete = AsyncMock(side_effect=_complete_side)

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # Both tools should have been called
        tool_a.execute.assert_awaited_once()
        tool_b.execute.assert_awaited_once()
        tool_start_events = [e for e in events if e.event == "tool_start"]
        assert len(tool_start_events) == 2

    @pytest.mark.asyncio
    async def test_react_loop_no_tool_calls_emits_token(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
    ) -> None:
        """If the LLM returns no tool calls, the text is emitted as a token."""
        chunks = [_make_stream_chunk(content="The answer is clear.")]
        mock_llm.complete = AsyncMock(return_value=_async_iter(chunks))

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        token_events = [e for e in events if e.event == "token"]
        assert len(token_events) >= 1
        assert "answer" in token_events[0].data

    @pytest.mark.asyncio
    async def test_react_loop_stops_after_max_iterations(
        self,
        agent: RAGAgent,
        mock_llm: AsyncMock,
        mock_tool: MagicMock,
    ) -> None:
        """Loop terminates after MAX_REACT_ITERATIONS even if LLM keeps returning tool calls."""
        tc_delta = _make_tool_call_delta(
            index=0, call_id="call_loop", name="hybrid_search", arguments='{"query": "test"}'
        )
        tool_chunks = [_make_stream_chunk(content=None, tool_calls=[tc_delta])]

        # Always return tool calls → loop must eventually stop
        mock_llm.complete = AsyncMock(
            side_effect=[_async_iter(list(tool_chunks)) for _ in range(MAX_REACT_ITERATIONS + 5)]
        )

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        # LLM should be called at most MAX_REACT_ITERATIONS times
        assert mock_llm.complete.call_count <= MAX_REACT_ITERATIONS


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
        chunks = [_make_stream_chunk(content="AI stands for Artificial Intelligence.")]
        mock_llm.complete = AsyncMock(return_value=_async_iter(chunks))

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
        chunks = [_make_stream_chunk(content="Answer.")]
        mock_llm.complete = AsyncMock(return_value=_async_iter(chunks))

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
        chunks = [_make_stream_chunk(content="The answer is simple.")]
        mock_llm.complete = AsyncMock(return_value=_async_iter(chunks))

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
        chunks = [_make_stream_chunk(content="Done.")]
        mock_llm.complete = AsyncMock(return_value=_async_iter(chunks))

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
        chunks = [
            _make_stream_chunk("The "),
            _make_stream_chunk("answer "),
            _make_stream_chunk("is "),
            _make_stream_chunk("42."),
        ]
        mock_llm.complete = AsyncMock(return_value=_async_iter(chunks))

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        token_events = []
        async for event in agent.chat(request, uuid.uuid4()):
            if event.event == "token":
                token_events.append(event.data)

        # All chunks are emitted as a single token event (buffered)
        full = "".join(token_events)
        assert full == "The answer is 42."
