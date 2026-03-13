"""Tests for LLM provider wrapper."""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.infra.llm import LLMProvider


class TestLLMProviderInit:
    """Tests for LLM provider initialization."""

    def test_initial_state(self) -> None:
        """Provider should start uninitialized."""
        provider = LLMProvider()
        assert provider._initialized is False

    @patch("app.infra.llm.get_settings")
    @patch("app.infra.llm.litellm")
    def test_initialize_sets_api_keys(
        self,
        mock_litellm: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """initialize() should configure LiteLLM with API keys."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "sk-ant-test"
        mock_settings.openai_api_key = "sk-oai-test"
        mock_settings.debug = False
        mock_settings.default_model = "anthropic/claude-sonnet-4-20250514"
        mock_settings.fallback_model = "openai/gpt-4o"
        mock_get_settings.return_value = mock_settings

        provider = LLMProvider()
        provider.initialize()

        assert provider._initialized is True
        assert mock_litellm.anthropic_key == "sk-ant-test"
        assert mock_litellm.openai_key == "sk-oai-test"


class TestLLMProviderComplete:
    """Tests for completion calls."""

    @pytest.mark.asyncio
    @patch("app.infra.llm.get_settings")
    @patch("app.infra.llm.acompletion")
    async def test_complete_uses_primary_model(
        self,
        mock_acompletion: AsyncMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """complete() should use the default (primary) model."""
        mock_settings = MagicMock()
        mock_settings.default_model = "anthropic/claude-sonnet-4-20250514"
        mock_settings.fallback_model = "openai/gpt-4o"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_acompletion.return_value = mock_response

        provider = LLMProvider()
        provider._initialized = True

        messages = [{"role": "user", "content": "Hello"}]
        result = await provider.complete(messages=messages)

        mock_acompletion.assert_called_once_with(
            model="anthropic/claude-sonnet-4-20250514",
            messages=messages,
            temperature=0.0,
            max_tokens=4096,
            stream=False,
        )
        assert result is mock_response

    @pytest.mark.asyncio
    @patch("app.infra.llm.get_settings")
    @patch("app.infra.llm.acompletion")
    async def test_complete_falls_back_on_primary_failure(
        self,
        mock_acompletion: AsyncMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """complete() should try fallback model when primary fails."""
        mock_settings = MagicMock()
        mock_settings.default_model = "anthropic/claude-sonnet-4-20250514"
        mock_settings.fallback_model = "openai/gpt-4o"
        mock_get_settings.return_value = mock_settings

        mock_fallback_response = MagicMock()
        mock_acompletion.side_effect = [
            Exception("Primary model rate limited"),
            mock_fallback_response,
        ]

        provider = LLMProvider()
        provider._initialized = True

        messages = [{"role": "user", "content": "Hello"}]
        result = await provider.complete(messages=messages)

        assert mock_acompletion.call_count == 2
        assert result is mock_fallback_response

    @pytest.mark.asyncio
    @patch("app.infra.llm.get_settings")
    @patch("app.infra.llm.acompletion")
    async def test_complete_raises_when_both_fail(
        self,
        mock_acompletion: AsyncMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """complete() should raise when both primary and fallback fail."""
        mock_settings = MagicMock()
        mock_settings.default_model = "anthropic/claude-sonnet-4-20250514"
        mock_settings.fallback_model = "openai/gpt-4o"
        mock_get_settings.return_value = mock_settings

        mock_acompletion.side_effect = Exception("All models down")

        provider = LLMProvider()
        provider._initialized = True

        messages = [{"role": "user", "content": "Hello"}]
        with pytest.raises(Exception, match="All models down"):
            await provider.complete(messages=messages)


class TestLLMProviderHealthCheck:
    """Tests for health check."""

    @patch("app.infra.llm.get_settings")
    def test_health_check_when_initialized(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Should return configured status when initialized."""
        mock_settings = MagicMock()
        mock_settings.default_model = "anthropic/claude-sonnet-4-20250514"
        mock_settings.fallback_model = "openai/gpt-4o"
        mock_settings.anthropic_api_key = "sk-ant-test"
        mock_settings.openai_api_key = "sk-oai-test"
        mock_get_settings.return_value = mock_settings

        provider = LLMProvider()
        provider._initialized = True

        result = provider.health_check()

        assert result["status"] == "configured"
        assert result["anthropic_key_set"] is True
        assert result["openai_key_set"] is True

    @patch("app.infra.llm.get_settings")
    def test_health_check_when_not_initialized(
        self,
        mock_get_settings: MagicMock,
    ) -> None:
        """Should return not_initialized when not started."""
        mock_settings = MagicMock()
        mock_settings.default_model = "test"
        mock_settings.fallback_model = "test"
        mock_settings.anthropic_api_key = ""
        mock_settings.openai_api_key = ""
        mock_get_settings.return_value = mock_settings

        provider = LLMProvider()

        result = provider.health_check()

        assert result["status"] == "not_initialized"
