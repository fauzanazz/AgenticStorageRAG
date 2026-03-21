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
    source_url: str | None = None


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageCreate(BaseModel):
    """User message input."""

    content: str = Field(..., min_length=1, max_length=10000)


class AddMessageRequest(BaseModel):
    """Add a message to a conversation (used by the Next.js agent route)."""

    role: str = "user"
    content: str = ""
    citations: list[Citation] | None = None
    tool_calls: list[dict] | None = None
    thinking_blocks: list[str] | None = None


class UpdateTitleRequest(BaseModel):
    """Update a conversation title."""

    title: str = Field("", max_length=255)


class MessageResponse(BaseModel):
    """Chat message response."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] = []
    tool_calls: list[dict] | None = None
    thinking_blocks: list[str] | None = None
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
    model: str | None = Field(
        None, description="Model override for this request (e.g. 'anthropic/claude-sonnet-4-20250514')"
    )
    enable_thinking: bool = Field(
        False, description="Enable extended thinking (real API-level reasoning) for supported models"
    )
    vector_weight: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Weight for vector vs graph retrieval"
    )
    attachment_ids: list[str] = Field(
        default_factory=list,
        description="IDs of uploaded attachments to include as context",
    )


class ChatStreamEvent(BaseModel):
    """Server-sent event for streaming chat responses."""

    event: str = Field(
        ..., description="Event type: token | thinking | tool_start | tool_result | citation | message_created | artifact_start | artifact_delta | artifact_end | done | error"
    )
    data: str = Field("", description="Event payload")


class AgentToolCall(BaseModel):
    """Record of an agent tool invocation."""

    tool_name: str
    arguments: dict = {}
    result_summary: str = ""
    duration_ms: int = 0
    results: list[dict] = []


# ---------------------------------------------------------------------------
# Friendly tool name mapping (for narrative UX)
# ---------------------------------------------------------------------------

TOOL_FRIENDLY_NAMES: dict[str, str] = {
    "hybrid_search": "Searching documents and knowledge graph",
    "vector_search": "Searching documents",
    "graph_search": "Searching knowledge graph",
    "generate_document": "Generating document",
    "fetch_document": "Fetching full document",
}


def friendly_tool_name(tool_name: str) -> str:
    """Return a user-friendly label for a tool name."""
    return TOOL_FRIENDLY_NAMES.get(tool_name, f"Using {tool_name}")


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


class AttachmentResponse(BaseModel):
    """Response for an uploaded attachment."""

    id: uuid.UUID
    filename: str
    size: int
    mime_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DriveAttachmentRequest(BaseModel):
    """Request to attach files from Google Drive."""

    file_ids: list[str] = Field(..., min_length=1, max_length=5)


# ---------------------------------------------------------------------------
# Narrative SSE event data schemas
# ---------------------------------------------------------------------------


class ToolStartData(BaseModel):
    """Payload for a ``tool_start`` SSE event."""

    tool_name: str
    tool_label: str  # friendly name
    arguments: dict = {}


class ToolResultData(BaseModel):
    """Payload for a ``tool_result`` SSE event."""

    tool_name: str
    tool_label: str
    summary: str = ""
    count: int = 0
    duration_ms: int = 0
    error: str | None = None
    results: list[dict] = []


# ---------------------------------------------------------------------------
# Artifact schemas
# ---------------------------------------------------------------------------


class ArtifactResponse(BaseModel):
    """Artifact response."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    user_id: uuid.UUID
    type: str = "markdown"
    title: str
    content: str
    language: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactStartData(BaseModel):
    """Payload for an ``artifact_start`` SSE event."""

    artifact_id: str
    title: str
    type: str = "markdown"


class ArtifactDeltaData(BaseModel):
    """Payload for an ``artifact_delta`` SSE event."""

    artifact_id: str
    content: str


class ArtifactEndData(BaseModel):
    """Payload for an ``artifact_end`` SSE event."""

    artifact_id: str
    title: str
    type: str = "markdown"
    content_length: int = 0
