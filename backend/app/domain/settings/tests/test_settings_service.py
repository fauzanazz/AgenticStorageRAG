import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.settings.schemas import (
    ApiKeyStatus,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.domain.settings.service import SettingsService


# -----------------------------------------------------------------------
# Unit tests for SettingsService._apply_key
# -----------------------------------------------------------------------


class TestApplyKey:
    def test_empty_string_returns_existing(self):
        existing = "encrypted_value"
        assert SettingsService._apply_key("", existing) == existing

    def test_empty_string_with_none_existing_returns_none(self):
        assert SettingsService._apply_key("", None) is None

    def test_none_clears_key(self):
        assert SettingsService._apply_key(None, "some_enc") is None

    def test_none_on_already_none_stays_none(self):
        assert SettingsService._apply_key(None, None) is None

    def test_new_value_encrypts(self):
        with patch(
            "app.domain.settings.service.encrypt_value", return_value="enc"
        ) as mock_enc:
            result = SettingsService._apply_key("sk-new-key", None)
            mock_enc.assert_called_once_with("sk-new-key")
            assert result == "enc"

    def test_new_value_replaces_existing(self):
        with patch(
            "app.domain.settings.service.encrypt_value", return_value="new_enc"
        ):
            result = SettingsService._apply_key("sk-new-key", "old_enc")
            assert result == "new_enc"


# -----------------------------------------------------------------------
# Unit tests for SettingsService._to_response
# -----------------------------------------------------------------------


class TestToResponse:
    def _make_row(self, anthropic=None, openai=None, dashscope=None):
        row = MagicMock()
        row.chat_model = "anthropic/claude-sonnet-4-20250514"
        row.ingestion_model = "dashscope/qwen3-max"
        row.embedding_model = "openai/text-embedding-3-small"
        row.anthropic_api_key_enc = anthropic
        row.openai_api_key_enc = openai
        row.dashscope_api_key_enc = dashscope
        return row

    def test_has_key_true_when_enc_present(self):
        row = self._make_row(anthropic="enc_key")
        resp = SettingsService._to_response(row)
        assert resp.anthropic_api_key.has_key is True
        assert resp.openai_api_key.has_key is False
        assert resp.dashscope_api_key.has_key is False

    def test_has_key_false_when_all_none(self):
        row = self._make_row()
        resp = SettingsService._to_response(row)
        assert resp.anthropic_api_key.has_key is False
        assert resp.openai_api_key.has_key is False
        assert resp.dashscope_api_key.has_key is False

    def test_all_keys_set(self):
        row = self._make_row(anthropic="a", openai="b", dashscope="c")
        resp = SettingsService._to_response(row)
        assert resp.anthropic_api_key.has_key is True
        assert resp.openai_api_key.has_key is True
        assert resp.dashscope_api_key.has_key is True

    def test_model_fields_match(self):
        row = self._make_row()
        resp = SettingsService._to_response(row)
        assert resp.chat_model == "anthropic/claude-sonnet-4-20250514"
        assert resp.ingestion_model == "dashscope/qwen3-max"
        assert resp.embedding_model == "openai/text-embedding-3-small"


# -----------------------------------------------------------------------
# Unit tests for SettingsService.upsert_model_settings (mocked DB)
# -----------------------------------------------------------------------


class TestSettingsServiceUpsert:
    @pytest.mark.asyncio
    async def test_upsert_sets_openai_key_and_clears_dashscope(self):
        mock_db = AsyncMock()
        service = SettingsService(db=mock_db)
        user_id = uuid.uuid4()

        mock_row = MagicMock()
        mock_row.chat_model = "openai/gpt-4o"
        mock_row.ingestion_model = "openai/gpt-4o"
        mock_row.embedding_model = "openai/text-embedding-3-small"
        mock_row.anthropic_api_key_enc = None
        mock_row.openai_api_key_enc = None
        mock_row.dashscope_api_key_enc = "old_dashscope_enc"

        with patch.object(service, "_get_or_create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_row
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            request = UpdateModelSettingsRequest(
                chat_model="openai/gpt-4o",
                ingestion_model="openai/gpt-4o",
                embedding_model="openai/text-embedding-3-small",
                anthropic_api_key="",        # unchanged
                openai_api_key="sk-test-key", # set new
                dashscope_api_key=None,       # clear
            )

            with patch(
                "app.domain.settings.service.encrypt_value", return_value="enc_openai"
            ):
                result = await service.upsert_model_settings(user_id, request)

        assert mock_row.openai_api_key_enc == "enc_openai"
        assert mock_row.dashscope_api_key_enc is None
        assert mock_row.anthropic_api_key_enc is None  # unchanged from None

    @pytest.mark.asyncio
    async def test_upsert_model_fields_only(self):
        mock_db = AsyncMock()
        service = SettingsService(db=mock_db)
        user_id = uuid.uuid4()

        mock_row = MagicMock()
        mock_row.chat_model = "dashscope/qwen3-max"
        mock_row.ingestion_model = "dashscope/qwen3-max"
        mock_row.embedding_model = "openai/text-embedding-3-small"
        mock_row.anthropic_api_key_enc = None
        mock_row.openai_api_key_enc = None
        mock_row.dashscope_api_key_enc = None

        with patch.object(service, "_get_or_create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_row
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            request = UpdateModelSettingsRequest(
                chat_model="anthropic/claude-sonnet-4-20250514",
                # all keys unchanged (empty string default)
            )

            result = await service.upsert_model_settings(user_id, request)

        assert mock_row.chat_model == "anthropic/claude-sonnet-4-20250514"
