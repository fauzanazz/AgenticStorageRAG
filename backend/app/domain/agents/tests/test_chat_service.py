"""Tests for chat service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
    return datetime.now(UTC)


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
    async def test_success(self, service: ChatService, mock_db: AsyncMock, now: datetime) -> None:
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
    async def test_empty_list(self, service: ChatService, mock_db: AsyncMock) -> None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        # list_conversations uses result.all() not result.scalars().all()
        result_mock.all.return_value = []
        mock_db.execute.return_value = result_mock

        result = await service.list_conversations(uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_list_with_conversations(
        self, service: ChatService, mock_db: AsyncMock, now: datetime
    ) -> None:
        """list_conversations() should return conversations with message counts."""
        user_id = uuid.uuid4()
        conv1 = MagicMock(spec=Conversation)
        conv1.id = uuid.uuid4()
        conv1.user_id = user_id
        conv1.title = "First conversation"
        conv1.created_at = now
        conv1.updated_at = now

        conv2 = MagicMock(spec=Conversation)
        conv2.id = uuid.uuid4()
        conv2.user_id = user_id
        conv2.title = "Second conversation"
        conv2.created_at = now
        conv2.updated_at = now

        # list_conversations uses result.all() which returns (conv, msg_count) tuples
        result_mock = MagicMock()
        result_mock.all.return_value = [(conv1, 3), (conv2, 0)]
        mock_db.execute.return_value = result_mock

        result = await service.list_conversations(user_id)

        assert len(result) == 2
        assert result[0].title == "First conversation"
        assert result[0].message_count == 3
        assert result[1].title == "Second conversation"
        assert result[1].message_count == 0


class TestDeleteConversation:
    """Tests for deleting conversation."""

    @pytest.mark.asyncio
    async def test_not_found(self, service: ChatService, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None

        with pytest.raises(ConversationNotFoundError):
            await service.delete_conversation(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_access_denied(self, service: ChatService, mock_db: AsyncMock) -> None:
        conv = MagicMock(spec=Conversation)
        conv.user_id = uuid.uuid4()
        mock_db.get.return_value = conv

        with pytest.raises(ConversationAccessDenied):
            await service.delete_conversation(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_success(self, service: ChatService, mock_db: AsyncMock) -> None:
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
    async def test_access_denied(self, service: ChatService, mock_db: AsyncMock) -> None:
        conv = MagicMock(spec=Conversation)
        conv.user_id = uuid.uuid4()
        mock_db.get.return_value = conv

        with pytest.raises(ConversationAccessDenied):
            await service.get_messages(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_success(self, service: ChatService, mock_db: AsyncMock, now: datetime) -> None:
        """get_messages() should return deserialized messages with citations."""
        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()

        conv = MagicMock(spec=Conversation)
        conv.user_id = user_id
        mock_db.get.return_value = conv

        msg = MagicMock(spec=Message)
        msg.id = uuid.uuid4()
        msg.conversation_id = conv_id
        msg.role = "assistant"
        msg.content = "Answer with citation"
        msg.citations_json = (
            '[{"content_snippet":"test","source_type":"vector","relevance_score":0.9}]'
        )
        msg.tool_calls_json = None
        msg.thinking_blocks_json = None
        msg.steps_json = None
        msg.token_count = 10
        msg.created_at = now

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [msg]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await service.get_messages(conv_id, user_id)

        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].content == "Answer with citation"
        assert len(result[0].citations) == 1
        assert result[0].citations[0].source_type == "vector"
