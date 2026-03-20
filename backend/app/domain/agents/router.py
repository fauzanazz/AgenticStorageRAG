"""Agent domain API router.

Endpoints for chat, conversation management, and streaming responses.
Uses Server-Sent Events (SSE) for streaming agent responses.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_user_model_settings
from app.domain.agents.chat_service import ChatService
from app.domain.agents.exceptions import (
    AgentBaseError,
    ConversationAccessDenied,
    ConversationNotFoundError,
)
from app.domain.agents.rag_agent import RAGAgent
from app.domain.agents.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
)
from app.domain.agents.tools import (
    GraphSearchTool,
    HybridSearchTool,
    VectorSearchTool,
)
from app.domain.auth.models import User
from app.domain.knowledge.graph_service import GraphService
from app.domain.knowledge.hybrid_retriever import HybridRetriever
from app.domain.knowledge.vector_service import VectorService
from app.domain.settings.models import UserModelSettings
from app.infra.llm import llm_provider
from app.infra.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# ── Dependency helpers ──────────────────────────────────────────────────


def _build_agent(
    db: AsyncSession,
    user_settings: UserModelSettings | None = None,
    model_override: str | None = None,
) -> RAGAgent:
    """Build the RAG agent with all tools wired up.

    When ``user_settings`` is provided the agent uses the user's own models
    and API keys via a scoped LLM provider.  Falls back to server defaults
    when ``user_settings`` is None.
    """
    # Resolve the LLM to use for this request
    effective_llm = (
        llm_provider.with_user_settings(user_settings)
        if user_settings is not None
        else llm_provider
    )

    # Resolve the embedding model for VectorService
    embedding_model = (
        user_settings.embedding_model if user_settings is not None else None
    )

    graph_service = GraphService(db=db, neo4j=neo4j_client)
    vector_service = VectorService(db=db, embedding_model=embedding_model)
    hybrid_retriever = HybridRetriever(
        vector_service=vector_service,
        graph_service=graph_service,
    )

    tools = [
        GraphSearchTool(graph_service),
        VectorSearchTool(vector_service),
        HybridSearchTool(hybrid_retriever),
    ]

    chat_service = ChatService(db=db)
    return RAGAgent(
        llm=effective_llm,
        chat_service=chat_service,
        tools=tools,
        db=db,
        model_override=model_override,
    )


def _get_chat_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db=db)


# ── Chat endpoint (SSE streaming) ─────────────────────────────────────


@router.post("/stream")
async def chat_stream(
    chat_request: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_settings: UserModelSettings | None = Depends(get_user_model_settings),
) -> StreamingResponse:
    """Stream a chat response using Server-Sent Events.

    The agent autonomously selects retrieval tools, performs search,
    and streams the response with citations.

    Event types:
    - `conversation_created`: New conversation ID
    - `tool_call`: Agent tool invocation record
    - `token`: Incremental response text
    - `citation`: Source citation
    - `done`: Final event with metadata
    - `error`: Error event
    """
    agent = _build_agent(db, user_settings=user_settings, model_override=chat_request.model)

    async def event_generator():
        async for event in agent.chat(chat_request, user.id):
            if await request.is_disconnected():
                logger.info("SSE client disconnected, stopping stream")
                break
            # SSE spec: multi-line data needs each line prefixed with "data: "
            data_lines = "\n".join(
                f"data: {line}" for line in event.data.split("\n")
            )
            yield f"event: {event.event}\n{data_lines}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Non-streaming chat endpoint ───────────────────────────────────────


@router.post("/message", response_model=MessageResponse)
async def chat_message(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_settings: UserModelSettings | None = Depends(get_user_model_settings),
) -> MessageResponse:
    """Send a message and get a complete (non-streaming) response.

    Useful for programmatic clients that don't support SSE.
    """
    agent = _build_agent(db, user_settings=user_settings, model_override=request.model)
    chat_service = ChatService(db=db)

    # Collect all events
    full_content = ""
    citations = []
    conversation_id = request.conversation_id

    try:
        async for event in agent.chat(request, user.id):
            if event.event == "token":
                full_content += event.data
            elif event.event == "citation":
                try:
                    citations.append(json.loads(event.data))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse citation: %s", event.data)
            elif event.event == "conversation_created":
                try:
                    data = json.loads(event.data)
                    conversation_id = uuid.UUID(data["conversation_id"])
                except (json.JSONDecodeError, KeyError, ValueError):
                    logger.warning("Failed to parse conversation_created event")
            elif event.event == "error":
                try:
                    error_data = json.loads(event.data)
                    raise HTTPException(status_code=500, detail=error_data.get("error", "Agent error"))
                except json.JSONDecodeError:
                    raise HTTPException(status_code=500, detail="Agent error")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Non-streaming chat failed")
        raise HTTPException(status_code=500, detail="Agent execution failed") from e

    if not conversation_id:
        raise HTTPException(status_code=500, detail="No conversation created")

    # Get the last assistant message from the conversation
    try:
        stmt_messages = await chat_service.get_messages(
            conversation_id, user.id, limit=100
        )
        assistant_messages = [m for m in stmt_messages if m.role == "assistant"]
        if assistant_messages:
            return assistant_messages[-1]
    except (ConversationNotFoundError, ConversationAccessDenied):
        pass

    # Fallback: construct response from collected data
    return MessageResponse(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=full_content or "I couldn't generate a response.",
        citations=[],
        token_count=len(full_content) // 4,
        created_at=datetime.now(timezone.utc),
    )


# ── Conversation CRUD ─────────────────────────────────────────────────


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> list[ConversationResponse]:
    """List user's conversations, newest first."""
    return await chat.list_conversations(user.id, limit)


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> ConversationResponse:
    """Create a new conversation."""
    return await chat.create_conversation(user.id, body.title)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> ConversationResponse:
    """Get conversation details."""
    try:
        return await chat.get_conversation(conversation_id, user.id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> None:
    """Delete a conversation and all its messages."""
    try:
        await chat.delete_conversation(conversation_id, user.id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def get_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> list[MessageResponse]:
    """Get message history for a conversation."""
    try:
        return await chat.get_messages(conversation_id, user.id, limit)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e
