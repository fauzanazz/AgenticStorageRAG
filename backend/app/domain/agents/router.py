"""Agent domain API router.

Endpoints for chat, conversation management, and streaming responses.
Uses Server-Sent Events (SSE) for streaming agent responses.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_user_model_settings
from app.domain.agents.attachments import (
    EXTENSION_TO_MIME,
    AttachmentService,
    AttachmentTooLargeError,
    UnsupportedAttachmentTypeError,
)
from app.domain.agents.chat_service import ChatService
from app.domain.agents.exceptions import (
    ArtifactNotFoundError,
    ConversationAccessDenied,
    ConversationNotFoundError,
)
from app.domain.agents.interfaces import IRAGAgent
from app.domain.agents.rag_agent import RAGAgent
from app.domain.agents.schemas import (
    AddMessageRequest,
    ArtifactResponse,
    AttachmentResponse,
    ChatRequest,
    ConversationCreate,
    ConversationResponse,
    DriveAttachmentRequest,
    EnrichCitationsRequest,
    FetchDocumentRequest,
    GenerateDocumentRequest,
    MessageResponse,
    UpdateTitleRequest,
)
from app.domain.agents.tools import FetchDocumentTool, GenerateDocumentTool, HybridSearchTool
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
) -> IRAGAgent:
    """Build the RAG agent with all tools wired up.

    When ``user_settings`` is provided the agent uses the user's own models
    and API keys via a scoped LLM provider.  Falls back to server defaults
    when ``user_settings`` is None.

    If ``user_settings.use_claude_code`` is True, returns a
    ``ClaudeCodeAgent`` which delegates the ReAct loop to the local
    ``claude`` CLI binary via the Claude Agent SDK.
    """
    # Resolve the LLM to use for this request
    effective_llm = (
        llm_provider.with_user_settings(user_settings)
        if user_settings is not None
        else llm_provider
    )

    # Resolve the embedding model for VectorService
    embedding_model = user_settings.embedding_model if user_settings is not None else None

    graph_service = GraphService(db=db, neo4j=neo4j_client)
    vector_service = VectorService(db=db, embedding_model=embedding_model)
    hybrid_retriever = HybridRetriever(
        vector_service=vector_service,
        graph_service=graph_service,
    )

    tools = [
        HybridSearchTool(hybrid_retriever),
        GenerateDocumentTool(llm=effective_llm, model_override=model_override),
        FetchDocumentTool(db=db),
    ]

    chat_service = ChatService(db=db)

    # Use Claude Code agent if the user opted in
    if user_settings is not None and user_settings.use_claude_code:
        from app.infra.claude_code import ClaudeCodeAgent

        return ClaudeCodeAgent(
            chat_service=chat_service,
            tools=tools,
            db=db,
        )

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
            data_lines = "\n".join(f"data: {line}" for line in event.data.split("\n"))
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
                    raise HTTPException(
                        status_code=500, detail=error_data.get("error", "Agent error")
                    )
                except json.JSONDecodeError:
                    raise HTTPException(status_code=500, detail="Agent error") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Non-streaming chat failed")
        raise HTTPException(status_code=500, detail="Agent execution failed") from e

    if not conversation_id:
        raise HTTPException(status_code=500, detail="No conversation created")

    # Get the last assistant message from the conversation
    try:
        stmt_messages = await chat_service.get_messages(conversation_id, user.id, limit=100)
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
        created_at=datetime.now(UTC),
    )


# ── Attachment endpoints ─────────────────────────────────────────────


@router.post("/attachments", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    """Upload a file attachment for use in chat messages."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    content = await file.read()

    # Always derive MIME type from extension — never trust client Content-Type
    import os

    ext = os.path.splitext(file.filename)[1].lower()
    mime_type = EXTENSION_TO_MIME.get(ext)
    if not mime_type:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    service = AttachmentService(db)
    try:
        attachment = await service.upload(user.id, content, file.filename, mime_type)
        await db.commit()
        return AttachmentResponse.model_validate(attachment)
    except (AttachmentTooLargeError, UnsupportedAttachmentTypeError) as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post(
    "/attachments/from-drive",
    response_model=list[AttachmentResponse],
    status_code=201,
)
async def attach_from_drive(
    body: DriveAttachmentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AttachmentResponse]:
    """Download files from Google Drive and attach them for chat."""
    from sqlalchemy import select as sa_select

    from app.domain.auth.models import OAuthAccount

    result = await db.execute(
        sa_select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "google",
        )
    )
    oauth = result.scalar_one_or_none()
    if not oauth:
        raise HTTPException(
            status_code=400,
            detail="Google Drive not connected. Please connect your Google account in settings.",
        )

    from app.domain.ingestion.drive_connector import GoogleDriveConnector
    from app.infra.encryption import decrypt_value

    if not oauth.access_token_enc:
        raise HTTPException(
            status_code=401,
            detail="Google OAuth access token is missing. Please reconnect your Google account.",
        )

    connector = GoogleDriveConnector.from_user_tokens(
        access_token=decrypt_value(oauth.access_token_enc),
        refresh_token=decrypt_value(oauth.refresh_token_enc) if oauth.refresh_token_enc else None,
    )

    service = AttachmentService(db)
    try:
        attachments = await service.upload_from_drive(user.id, body.file_ids, connector)
        await db.commit()
        return [AttachmentResponse.model_validate(a) for a in attachments]
    except Exception as e:
        logger.exception("Failed to attach files from Drive")
        raise HTTPException(status_code=500, detail=str(e)) from e


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


# ── Artifact endpoints ───────────────────────────────────────────────


@router.get(
    "/conversations/{conversation_id}/artifacts",
    response_model=list[ArtifactResponse],
)
async def list_artifacts(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> list[ArtifactResponse]:
    """List all artifacts for a conversation."""
    try:
        return await chat.get_artifacts_by_conversation(conversation_id, user.id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
async def add_message(
    conversation_id: uuid.UUID,
    body: AddMessageRequest,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> MessageResponse:
    """Add a message to a conversation (used by Next.js agent route)."""
    try:
        await chat.get_conversation(conversation_id, user.id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e

    return await chat.add_message(
        conversation_id=conversation_id,
        role=body.role,
        content=body.content,
        citations=body.citations,
        tool_calls=body.tool_calls,
        thinking_blocks=body.thinking_blocks,
    )


@router.patch("/conversations/{conversation_id}/title", status_code=204)
async def update_conversation_title(
    conversation_id: uuid.UUID,
    body: UpdateTitleRequest,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> None:
    """Update conversation title (used by Next.js agent route)."""
    try:
        await chat.get_conversation(conversation_id, user.id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e

    await chat.update_conversation_title(conversation_id, body.title)


@router.post("/tools/fetch-document")
async def proxy_fetch_document(
    body: FetchDocumentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Proxy fetch-document tool for the Next.js agent route."""
    tool = FetchDocumentTool(db=db)
    return await tool.execute(**body.model_dump(exclude_none=True))


@router.post("/tools/generate-document")
async def proxy_generate_document(
    body: GenerateDocumentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_settings: UserModelSettings | None = Depends(get_user_model_settings),
) -> dict:
    """Proxy generate-document tool for the Next.js agent route (non-streaming)."""
    effective_llm = (
        llm_provider.with_user_settings(user_settings)
        if user_settings is not None
        else llm_provider
    )
    tool = GenerateDocumentTool(llm=effective_llm)
    return await tool.execute(**body.model_dump(exclude_none=True))


@router.post("/tools/enrich-citations")
async def enrich_citations(
    body: EnrichCitationsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enrich citations with document names and source URLs."""
    from sqlalchemy import select as sa_select

    from app.domain.documents.models import Document, DocumentSource
    from app.infra.storage import StorageClient

    raw_citations = body.citations
    if not raw_citations:
        return {"citations": []}

    from app.domain.agents.schemas import Citation

    citations = [Citation(**c) for c in raw_citations]

    # For graph-only citations (no document_id), use entity_name as document_name
    for citation in citations:
        if not citation.document_id and citation.entity_name:
            citation.document_name = citation.entity_name

    doc_ids = list({c.document_id for c in citations if c.document_id})
    if doc_ids:
        result = await db.execute(sa_select(Document).where(Document.id.in_(doc_ids)))
        docs_by_id = {doc.id: doc for doc in result.scalars().all()}
        storage = StorageClient()

        for citation in citations:
            doc = docs_by_id.get(citation.document_id)
            if not doc:
                continue
            citation.document_name = doc.filename
            if doc.source == DocumentSource.GOOGLE_DRIVE:
                drive_file_id = (doc.metadata_ or {}).get("drive_file_id")
                if drive_file_id:
                    citation.source_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
            elif doc.storage_path:
                try:
                    citation.source_url = await storage.get_signed_url(
                        doc.storage_path, expires_in=3600
                    )
                except Exception:
                    logger.warning("Failed to generate signed URL for %s", doc.storage_path)

    return {"citations": [c.model_dump(mode="json") for c in citations]}


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> ArtifactResponse:
    """Get a single artifact."""
    try:
        return await chat.get_artifact(artifact_id, user.id)
    except ArtifactNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    chat: ChatService = Depends(_get_chat_service),
) -> StreamingResponse:
    """Download an artifact as a markdown file."""
    try:
        artifact = await chat.get_artifact(artifact_id, user.id)
    except ArtifactNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConversationAccessDenied as e:
        raise HTTPException(status_code=403, detail=e.message) from e

    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in artifact.title)
    filename = f"{safe_title}.md"

    return StreamingResponse(
        iter([artifact.content]),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
