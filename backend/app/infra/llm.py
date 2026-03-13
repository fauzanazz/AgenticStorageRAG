"""LiteLLM provider configuration.

Provides a unified interface for LLM calls with Anthropic Claude
as primary and OpenAI as fallback. Uses LiteLLM for provider abstraction.
"""

from __future__ import annotations

import logging
from typing import Any

import litellm
from litellm import acompletion, ModelResponse

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMProvider:
    """LLM provider with primary/fallback model support.

    Uses LiteLLM to abstract away provider differences.
    Claude is primary, OpenAI is fallback.
    """

    def __init__(self) -> None:
        self._initialized: bool = False

    def initialize(self) -> None:
        """Configure LiteLLM with API keys and settings."""
        settings = get_settings()

        # Set API keys
        if settings.anthropic_api_key:
            litellm.anthropic_key = settings.anthropic_api_key
        if settings.openai_api_key:
            litellm.openai_key = settings.openai_api_key

        # Configure LiteLLM behavior
        litellm.set_verbose = settings.debug
        litellm.drop_params = True  # Drop unsupported params silently
        litellm.modify_params = True  # Auto-adapt params per provider

        self._initialized = True
        logger.info(
            "LLM provider initialized (primary: %s, fallback: %s)",
            settings.default_model,
            settings.fallback_model,
        )

    @property
    def default_model(self) -> str:
        """Get the default (primary) model identifier."""
        return get_settings().default_model

    @property
    def fallback_model(self) -> str:
        """Get the fallback model identifier."""
        return get_settings().fallback_model

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse:
        """Send a completion request to the LLM.

        Args:
            messages: Chat messages in OpenAI format
            model: Model to use (defaults to primary model)
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            stream: Whether to stream the response
            **kwargs: Additional LiteLLM parameters

        Returns:
            LiteLLM ModelResponse

        Raises:
            Exception: If both primary and fallback models fail
        """
        if not self._initialized:
            self.initialize()

        target_model = model or self.default_model

        try:
            response = await acompletion(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs,
            )
            return response

        except Exception as primary_error:
            if target_model == self.fallback_model:
                raise

            logger.warning(
                "Primary model %s failed: %s. Falling back to %s",
                target_model,
                str(primary_error),
                self.fallback_model,
            )

            response = await acompletion(
                model=self.fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs,
            )
            return response

    async def complete_with_retry(
        self,
        messages: list[dict[str, str]],
        max_retries: int = 2,
        **kwargs: Any,
    ) -> ModelResponse:
        """Complete with automatic retry on failure.

        Tries the primary model, then fallback, with retries on each.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await self.complete(messages=messages, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning("LLM attempt %d/%d failed: %s", attempt + 1, max_retries + 1, e)

        raise last_error  # type: ignore[misc]

    def health_check(self) -> dict[str, Any]:
        """Return LLM provider health status."""
        settings = get_settings()
        return {
            "status": "configured" if self._initialized else "not_initialized",
            "primary_model": settings.default_model,
            "fallback_model": settings.fallback_model,
            "anthropic_key_set": bool(settings.anthropic_api_key),
            "openai_key_set": bool(settings.openai_api_key),
        }


# Module-level singleton (initialized via lifespan)
llm_provider = LLMProvider()
