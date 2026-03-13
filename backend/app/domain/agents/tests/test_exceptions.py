"""Tests for agent exceptions."""

from app.domain.agents.exceptions import (
    AgentBaseError,
    AgentExecutionError,
    ConversationAccessDenied,
    ConversationNotFoundError,
    MessageNotFoundError,
    ToolExecutionError,
)


class TestExceptions:
    """Tests for agent domain exceptions."""

    def test_base_error(self) -> None:
        err = AgentBaseError()
        assert str(err) == "Agent error"

    def test_conversation_not_found(self) -> None:
        err = ConversationNotFoundError("conv-123")
        assert "conv-123" in str(err)
        assert err.conversation_id == "conv-123"

    def test_message_not_found(self) -> None:
        err = MessageNotFoundError("msg-456")
        assert "msg-456" in str(err)
        assert err.message_id == "msg-456"

    def test_agent_execution_error(self) -> None:
        err = AgentExecutionError("LLM timeout")
        assert "LLM timeout" in str(err)

    def test_tool_execution_error(self) -> None:
        err = ToolExecutionError("graph_search", "Neo4j down")
        assert "graph_search" in str(err)
        assert "Neo4j down" in str(err)
        assert err.tool_name == "graph_search"

    def test_conversation_access_denied(self) -> None:
        err = ConversationAccessDenied()
        assert "Access denied" in str(err)
