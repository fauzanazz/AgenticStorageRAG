"""Agent domain interfaces.

Abstract base classes for agent components.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from collections.abc import Callable
from typing import Any

# Type alias for the SSE event emitter callback.
# Signature: emit_event(event_type: str, data_json: str) -> None
EventEmitter = Callable[[str, str], None] | None

from app.domain.agents.schemas import (
    ChatRequest,
    ChatStreamEvent,
    Citation,
    ConversationResponse,
    MessageResponse,
)


class IAgentTool(ABC):
    """Interface for agent tools.

    Tools are callable capabilities the agent can invoke autonomously.
    Each tool has a name, description (for the LLM), and an execute method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for the LLM to understand when to use it."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema dict describing this tool's input parameters."""
        ...

    @abstractmethod
    async def execute(self, emit_event: EventEmitter = None, **kwargs: Any) -> dict[str, Any]:
        """Execute the tool with given arguments.

        Args:
            emit_event: Optional callback to emit SSE events during execution.
                        Signature: (event_type: str, data_json: str) -> None.
                        Tools that don't need streaming can ignore this parameter.

        Returns:
            Dict with 'result' key containing the tool output.
        """
        ...


class IRAGAgent(ABC):
    """Interface for the RAG agent.

    The agent orchestrates tool selection, retrieval, reasoning,
    and response generation.
    """

    @abstractmethod
    async def chat(
        self,
        request: ChatRequest,
        user_id: uuid.UUID,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """Process a chat request and stream response events.

        Yields:
            ChatStreamEvent objects for each part of the response:
            - token: incremental text tokens
            - citation: source citations
            - tool_call: tool invocation records
            - done: final event with metadata
            - error: if something goes wrong
        """
        ...


class IChatService(ABC):
    """Interface for conversation/message persistence."""

    @abstractmethod
    async def create_conversation(
        self, user_id: uuid.UUID, title: str = "New conversation"
    ) -> ConversationResponse:
        """Create a new conversation."""
        ...

    @abstractmethod
    async def get_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> ConversationResponse:
        """Get conversation metadata."""
        ...

    @abstractmethod
    async def list_conversations(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[ConversationResponse]:
        """List user's conversations."""
        ...

    @abstractmethod
    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Delete a conversation and all its messages."""
        ...

    @abstractmethod
    async def update_conversation_title(
        self, conversation_id: uuid.UUID, title: str
    ) -> None:
        """Update a conversation's title."""
        ...

    @abstractmethod
    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[Citation] | None = None,
        tool_calls: list[dict] | None = None,
        thinking_blocks: list[str] | None = None,
    ) -> MessageResponse:
        """Add a message to a conversation."""
        ...

    @abstractmethod
    async def get_messages(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, limit: int = 100
    ) -> list[MessageResponse]:
        """Get message history for a conversation."""
        ...

    @abstractmethod
    async def create_artifact(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        content: str,
        type: str = "markdown",
        message_id: uuid.UUID | None = None,
        language: str | None = None,
    ) -> Any:
        """Create and persist an artifact linked to a conversation."""
        ...
