"""Tests for chat service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.agents.chat_service import ChatService
from app.domain.agents.exceptions import (
    ConversationAccessDenied,
    ConversationNotFoundError,
)
from app.domain.agents.models import Conversation, Message
from app.domain.agents.schemas import Citation


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> ChatService:
    return ChatService(db=mock_db)


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


class TestCreateConversation:
    """Tests for conversation creation."""

    @pytest.mark.asyncio
    async def test_create_success(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        user_id = uuid.uuid4()

        def set_defaults(conv: Conversation) -> None:
            conv.id = uuid.uuid4()
            conv.created_at = now
            conv.updated_at = now

        mock_db.add.side_effect = set_defaults

        result = await service.create_conversation(user_id, "Test Conv")
        assert result.title == "Test Conv"
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_default_title(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        def set_defaults(conv: Conversation) -> None:
            conv.id = uuid.uuid4()
            conv.created_at = now
            conv.updated_at = now

        mock_db.add.side_effect = set_defaults

        result = await service.create_conversation(uuid.uuid4())
        assert result.title == "New conversation"


class TestGetConversation:
    """Tests for getting conversation."""

    @pytest.mark.asyncio
    async def test_not_found(self, service: ChatService, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None

        with pytest.raises(ConversationNotFoundError):
            await service.get_conversation(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_access_denied(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        conv = MagicMock(spec=Conversation)
        conv.user_id = uuid.uuid4()
        mock_db.get.return_value = conv

        with pytest.raises(ConversationAccessDenied):
            await service.get_conversation(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_success(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()

        conv = MagicMock(spec=Conversation)
        conv.id = conv_id
        conv.user_id = user_id
        conv.title = "Test"
        conv.created_at = now
        conv.updated_at = now
        mock_db.get.return_value = conv

        # Mock message count query
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        mock_db.execute.return_value = count_result

        result = await service.get_conversation(conv_id, user_id)
        assert result.id == conv_id
        assert result.message_count == 5


class TestListConversations:
    """Tests for listing conversations."""

    @pytest.mark.asyncio
    async def test_empty_list(
        self, service: ChatService, mock_db: AsyncMock
    ) -> None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await service.list_conversations(uuid.uuid4())
        assert result == []


class TestDeleteConversation:
    """Tests for deleting conversation."""

    @pytest.mark.asyncio
    async def test_not_found(self, service: ChatService, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None

        with pytest.raises(ConversationNotFoundError):
            await service.delete_conversation(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_access_denied(
        self, service: ChatService, mock_db: AsyncMock
    ) -> None:
        conv = MagicMock(spec=Conversation)
        conv.user_id = uuid.uuid4()
        mock_db.get.return_value = conv

        with pytest.raises(ConversationAccessDenied):
            await service.delete_conversation(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_success(
        self, service: ChatService, mock_db: AsyncMock
    ) -> None:
        user_id = uuid.uuid4()
        conv = MagicMock(spec=Conversation)
        conv.user_id = user_id
        mock_db.get.return_value = conv

        await service.delete_conversation(uuid.uuid4(), user_id)
        mock_db.delete.assert_called_once_with(conv)


class TestAddMessage:
    """Tests for adding messages."""

    @pytest.mark.asyncio
    async def test_add_user_message(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        conv_id = uuid.uuid4()

        def set_defaults(msg: Message) -> None:
            msg.id = uuid.uuid4()
            msg.created_at = now

        mock_db.add.side_effect = set_defaults

        result = await service.add_message(
            conversation_id=conv_id,
            role="user",
            content="Hello!",
        )

        assert result.role == "user"
        assert result.content == "Hello!"
        assert result.conversation_id == conv_id

    @pytest.mark.asyncio
    async def test_add_message_with_citations(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        conv_id = uuid.uuid4()

        def set_defaults(msg: Message) -> None:
            msg.id = uuid.uuid4()
            msg.created_at = now

        mock_db.add.side_effect = set_defaults

        citations = [
            Citation(
                content_snippet="test snippet",
                source_type="vector",
                relevance_score=0.9,
            )
        ]

        result = await service.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="Here is the answer.",
            citations=citations,
        )

        assert result.role == "assistant"
        assert len(result.citations) == 1


class TestGetMessages:
    """Tests for getting messages."""

    @pytest.mark.asyncio
    async def test_not_found(self, service: ChatService, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None

        with pytest.raises(ConversationNotFoundError):
            await service.get_messages(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_access_denied(
        self, service: ChatService, mock_db: AsyncMock
    ) -> None:
        conv = MagicMock(spec=Conversation)
        conv.user_id = uuid.uuid4()
        mock_db.get.return_value = conv

        with pytest.raises(ConversationAccessDenied):
            await service.get_messages(uuid.uuid4(), uuid.uuid4())
