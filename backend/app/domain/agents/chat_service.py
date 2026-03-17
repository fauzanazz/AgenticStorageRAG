"""Chat service for conversation and message persistence.

Handles CRUD operations for conversations and messages,
ensuring user ownership checks.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select, func as sa_func, desc, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.agents.exceptions import (
    ConversationAccessDenied,
    ConversationNotFoundError,
)
from app.domain.agents.interfaces import IChatService
from app.domain.agents.models import Conversation, Message
from app.domain.agents.schemas import (
    Citation,
    ConversationResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)


class ChatService(IChatService):
    """Persistence layer for conversations and messages."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_conversation(
        self, user_id: uuid.UUID, title: str = "New conversation"
    ) -> ConversationResponse:
        """Create a new conversation."""
        conversation = Conversation(
            user_id=user_id,
            title=title,
        )
        self._db.add(conversation)
        await self._db.flush()
        await self._db.refresh(conversation)

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=0,
        )

    async def get_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> ConversationResponse:
        """Get conversation metadata with ownership check."""
        conversation = await self._db.get(Conversation, conversation_id)

        if not conversation:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.user_id != user_id:
            raise ConversationAccessDenied()

        # Count messages
        count_stmt = select(sa_func.count(Message.id)).where(
            Message.conversation_id == conversation_id
        )
        msg_count = (await self._db.execute(count_stmt)).scalar() or 0

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=msg_count,
        )

    async def list_conversations(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[ConversationResponse]:
        """List user's conversations, newest first.

        Uses a single query with subquery-based message count
        to avoid N+1 queries.
        """
        # Subquery for message counts
        msg_count_subq = (
            select(
                Message.conversation_id,
                sa_func.count(Message.id).label("msg_count"),
            )
            .group_by(Message.conversation_id)
            .subquery()
        )

        stmt = (
            select(
                Conversation,
                sa_func.coalesce(msg_count_subq.c.msg_count, 0).label("message_count"),
            )
            .outerjoin(
                msg_count_subq,
                Conversation.id == msg_count_subq.c.conversation_id,
            )
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        rows = result.all()

        return [
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=msg_count,
            )
            for conv, msg_count in rows
        ]

    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Delete a conversation (cascades to messages)."""
        conversation = await self._db.get(Conversation, conversation_id)

        if not conversation:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.user_id != user_id:
            raise ConversationAccessDenied()

        await self._db.delete(conversation)
        await self._db.flush()
        logger.info("Deleted conversation %s", conversation_id)

    async def update_conversation_title(
        self, conversation_id: uuid.UUID, title: str
    ) -> None:
        """Update a conversation's title.

        Used to set the title from the first user message.
        No ownership check -- called internally from the agent.
        """
        conversation = await self._db.get(Conversation, conversation_id)
        if conversation:
            conversation.title = title
            await self._db.flush()
            logger.debug("Updated conversation %s title: %s", conversation_id, title)

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[Citation] | None = None,
        tool_calls: list[dict] | None = None,
    ) -> MessageResponse:
        """Add a message to a conversation."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations_json=(
                json.dumps([c.model_dump() for c in citations])
                if citations
                else None
            ),
            tool_calls_json=json.dumps(tool_calls) if tool_calls else None,
            token_count=len(content) // 4,  # rough estimate
        )
        self._db.add(message)
        await self._db.flush()
        await self._db.refresh(message)

        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            citations=citations or [],
            tool_calls=tool_calls,
            token_count=message.token_count,
            created_at=message.created_at,
        )

    async def get_messages(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, limit: int = 100
    ) -> list[MessageResponse]:
        """Get message history for a conversation."""
        # Verify ownership
        conversation = await self._db.get(Conversation, conversation_id)
        if not conversation:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.user_id != user_id:
            raise ConversationAccessDenied()

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        messages = result.scalars().all()

        return [
            MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                citations=(
                    [Citation(**c) for c in json.loads(msg.citations_json)]
                    if msg.citations_json
                    else []
                ),
                tool_calls=(
                    json.loads(msg.tool_calls_json)
                    if msg.tool_calls_json
                    else None
                ),
                token_count=msg.token_count,
                created_at=msg.created_at,
            )
            for msg in messages
        ]
