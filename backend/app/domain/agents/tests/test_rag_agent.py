"""Tests for RAG agent."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.agents.rag_agent import RAGAgent
from app.domain.agents.schemas import (
    ChatRequest,
    ConversationResponse,
    MessageResponse,
)


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
def mock_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.name = "hybrid_search"
    tool.description = "Search everything"
    tool.execute.return_value = {
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
    return tool


@pytest.fixture
def agent(
    mock_llm: AsyncMock,
    mock_chat_service: AsyncMock,
    mock_tool: AsyncMock,
) -> RAGAgent:
    return RAGAgent(
        llm=mock_llm,
        chat_service=mock_chat_service,
        tools=[mock_tool],
    )


class TestParseToolCalls:
    """Tests for tool call parsing."""

    def test_parse_json_array(self, agent: RAGAgent) -> None:
        text = '[{"tool": "hybrid_search", "args": {"query": "AI"}}]'
        result = agent._parse_tool_calls(text)
        assert len(result) == 1
        assert result[0]["tool"] == "hybrid_search"

    def test_parse_code_block(self, agent: RAGAgent) -> None:
        text = '```json\n[{"tool": "vector_search", "args": {"query": "test"}}]\n```'
        result = agent._parse_tool_calls(text)
        assert len(result) == 1

    def test_parse_empty_array(self, agent: RAGAgent) -> None:
        result = agent._parse_tool_calls("[]")
        assert result == []

    def test_parse_invalid_json(self, agent: RAGAgent) -> None:
        result = agent._parse_tool_calls("not json at all")
        assert result == []

    def test_parse_embedded_array(self, agent: RAGAgent) -> None:
        text = 'I think we should use: [{"tool": "graph_search", "args": {}}] for this.'
        result = agent._parse_tool_calls(text)
        assert len(result) == 1


class TestRAGAgentChat:
    """Tests for RAG agent chat flow."""

    @pytest.mark.asyncio
    async def test_chat_creates_conversation(
        self, agent: RAGAgent, mock_llm: AsyncMock, mock_chat_service: AsyncMock
    ) -> None:
        """When no conversation_id is provided, a new one should be created."""
        # Mock LLM responses
        planning_response = MagicMock()
        planning_response.choices = [MagicMock()]
        planning_response.choices[0].message.content = "[]"

        synthesis_response = MagicMock()
        synthesis_response.choices = [MagicMock()]
        synthesis_response.choices[0].message.content = "AI stands for Artificial Intelligence."

        mock_llm.complete.side_effect = [planning_response]
        mock_llm.complete_with_retry.return_value = synthesis_response

        request = ChatRequest(message="What is AI?")
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        event_types = [e.event for e in events]
        assert "conversation_created" in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    async def test_chat_uses_existing_conversation(
        self, agent: RAGAgent, mock_llm: AsyncMock
    ) -> None:
        """When conversation_id is provided, should not create new."""
        planning_response = MagicMock()
        planning_response.choices = [MagicMock()]
        planning_response.choices[0].message.content = "[]"

        synthesis_response = MagicMock()
        synthesis_response.choices = [MagicMock()]
        synthesis_response.choices[0].message.content = "Answer."

        mock_llm.complete.side_effect = [planning_response]
        mock_llm.complete_with_retry.return_value = synthesis_response

        request = ChatRequest(
            message="test",
            conversation_id=uuid.uuid4(),
        )
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        event_types = [e.event for e in events]
        assert "conversation_created" not in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    async def test_chat_emits_tokens(
        self, agent: RAGAgent, mock_llm: AsyncMock
    ) -> None:
        """Response should be streamed as token events."""
        planning_response = MagicMock()
        planning_response.choices = [MagicMock()]
        planning_response.choices[0].message.content = "[]"

        synthesis_response = MagicMock()
        synthesis_response.choices = [MagicMock()]
        synthesis_response.choices[0].message.content = "The answer is simple."

        mock_llm.complete.side_effect = [planning_response]
        mock_llm.complete_with_retry.return_value = synthesis_response

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        token_events = []
        async for event in agent.chat(request, uuid.uuid4()):
            if event.event == "token":
                token_events.append(event.data)

        full_response = "".join(token_events)
        assert "answer" in full_response

    @pytest.mark.asyncio
    async def test_chat_handles_error(
        self, agent: RAGAgent, mock_chat_service: AsyncMock
    ) -> None:
        """Errors should be caught and emitted as error events."""
        mock_chat_service.add_message.side_effect = Exception("DB error")

        request = ChatRequest(message="test")
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        error_events = [e for e in events if e.event == "error"]
        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls(
        self, agent: RAGAgent, mock_llm: AsyncMock
    ) -> None:
        """When LLM requests tools, they should be executed."""
        planning_response = MagicMock()
        planning_response.choices = [MagicMock()]
        planning_response.choices[0].message.content = json.dumps([
            {"tool": "hybrid_search", "args": {"query": "test"}}
        ])

        synthesis_response = MagicMock()
        synthesis_response.choices = [MagicMock()]
        synthesis_response.choices[0].message.content = "Based on the search results..."

        mock_llm.complete.side_effect = [planning_response]
        mock_llm.complete_with_retry.return_value = synthesis_response

        request = ChatRequest(message="test", conversation_id=uuid.uuid4())
        events = []
        async for event in agent.chat(request, uuid.uuid4()):
            events.append(event)

        tool_call_events = [e for e in events if e.event == "tool_call"]
        assert len(tool_call_events) >= 1

        # Parse the tool call data
        tc_data = json.loads(tool_call_events[0].data)
        assert tc_data["tool_name"] == "hybrid_search"
