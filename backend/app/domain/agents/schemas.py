"""Agent domain schemas.

Pydantic models for chat API request/response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """A source citation attached to an agent response."""

    document_id: uuid.UUID | None = None
    document_name: str | None = None
    chunk_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    entity_name: str | None = None
    content_snippet: str = ""
    page_number: int | None = None
    source_type: str = "vector"  # vector | graph | both
    relevance_score: float = 0.0


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageCreate(BaseModel):
    """User message input."""

    content: str = Field(..., min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    """Chat message response."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] = []
    tool_calls: list[dict] | None = None
    token_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    """Create a new conversation."""

    title: str = Field("New conversation", max_length=255)


class ConversationResponse(BaseModel):
    """Conversation metadata response."""

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationResponse):
    """Conversation with full message history."""

    messages: list[MessageResponse] = []


# ---------------------------------------------------------------------------
# Chat / Streaming
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Full chat request with optional configuration."""

    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: uuid.UUID | None = Field(
        None, description="Existing conversation ID, or None to create new"
    )
    vector_weight: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Weight for vector vs graph retrieval"
    )


class ChatStreamEvent(BaseModel):
    """Server-sent event for streaming chat responses."""

    event: str = Field(
        ..., description="Event type: token | citation | tool_call | done | error"
    )
    data: str = Field("", description="Event payload")


class AgentToolCall(BaseModel):
    """Record of an agent tool invocation."""

    tool_name: str
    arguments: dict = {}
    result_summary: str = ""
    duration_ms: int = 0
