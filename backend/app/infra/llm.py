"""LiteLLM provider configuration.

Provides a unified interface for LLM calls with Alibaba DashScope Qwen
as primary and Anthropic Claude as fallback, with optional Google Gemini
support. Uses LiteLLM for provider abstraction.

Cost tracking is persisted to Redis so that all worker processes and the
API server share a single, consistent usage ledger.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import litellm
from litellm import ModelResponse, acompletion
from litellm import completion_cost as litellm_completion_cost

from app.config import get_settings

logger = logging.getLogger(__name__)

# Redis key prefix for LLM usage stats
_REDIS_USAGE_KEY = "llm:usage:totals"
_REDIS_MODEL_PREFIX = "llm:usage:model:"

# Timeout (seconds) for individual LLM calls — prevents indefinite hangs.
_LLM_TIMEOUT = 60.0

# DashScope international endpoint (Singapore region)
DASHSCOPE_API_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# Fallback per-token pricing (USD) for models where LiteLLM returns $0.
# Format: { model: (input_per_token, output_per_token) }
# Same rates as dashscope/qwen-max per DashScope docs.
_FALLBACK_PRICING: dict[str, tuple[float, float]] = {
    "dashscope/qwen3-max": (1.6e-06, 6.4e-06),
    "dashscope/qwen3-plus": (0.4e-06, 1.2e-06),
}


@dataclass
class UsageStats:
    """Accumulated LLM usage statistics (in-memory, resets on restart)."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_calls: int = 0
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        """Record a single completion call."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost
        self.total_calls += 1

        if model not in self.by_model:
            self.by_model[model] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
        self.by_model[model]["calls"] += 1
        self.by_model[model]["input_tokens"] += input_tokens
        self.by_model[model]["output_tokens"] += output_tokens
        self.by_model[model]["cost_usd"] += cost


class LLMProvider:
    """LLM provider with primary/fallback model support.

    Uses LiteLLM to abstract away provider differences.
    Qwen (DashScope) is primary, Claude is fallback.
    """

    def __init__(self) -> None:
        self._initialized: bool = False
        self.usage: UsageStats = UsageStats()

    def initialize(self) -> None:
        """Configure LiteLLM with API keys and settings."""
        settings = get_settings()

        # Set API keys
        if settings.anthropic_api_key:
            litellm.anthropic_key = settings.anthropic_api_key
        if settings.openai_api_key:
            litellm.openai_key = settings.openai_api_key
        if settings.dashscope_api_key:
            # LiteLLM reads DASHSCOPE_API_KEY env var for the dashscope/ prefix
            os.environ["DASHSCOPE_API_KEY"] = settings.dashscope_api_key
            os.environ["DASHSCOPE_API_BASE"] = DASHSCOPE_API_BASE
        if settings.gemini_api_key:
            # LiteLLM reads GEMINI_API_KEY env var for the gemini/ prefix
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
        if settings.openrouter_api_key:
            # LiteLLM reads OPENROUTER_API_KEY env var for the openrouter/ prefix
            os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key

        # Configure LiteLLM behavior
        litellm.set_verbose = False  # Disable verbose logging to reduce memory from log strings
        litellm.drop_params = True  # Drop unsupported params silently
        litellm.modify_params = True  # Auto-adapt params per provider
        litellm.cache = None  # Disable response caching to prevent memory accumulation

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

    @property
    def title_model(self) -> str:
        """Get the model used for generating chat session titles."""
        return get_settings().title_model

    @property
    def ingestion_model(self) -> str:
        """Get the dedicated ingestion model identifier.

        Defaults to claude-haiku-3-5 — a fast, cheap model with a 100K
        tokens/min rate limit, ideal for the structured JSON tasks in the
        ingestion pipeline (classify_file, KG extraction).
        """
        return get_settings().ingestion_model

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
            if stream:
                response = await acompletion(
                    model=target_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    timeout=_LLM_TIMEOUT,
                    **kwargs,
                )
            else:
                response = await asyncio.wait_for(
                    acompletion(
                        model=target_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        **kwargs,
                    ),
                    timeout=_LLM_TIMEOUT,
                )
                self._record_usage(target_model, response)
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

            try:
                if stream:
                    response = await acompletion(
                        model=self.fallback_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        timeout=_LLM_TIMEOUT,
                        **kwargs,
                    )
                else:
                    response = await asyncio.wait_for(
                        acompletion(
                            model=self.fallback_model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stream=False,
                            **kwargs,
                        ),
                        timeout=_LLM_TIMEOUT,
                    )
                    self._record_usage(self.fallback_model, response)
                return response
            except TimeoutError as exc:
                raise TimeoutError(
                    f"LLM call to fallback model {self.fallback_model} timed out after {_LLM_TIMEOUT}s"
                ) from exc

    def _record_usage(self, model: str, response: ModelResponse) -> None:
        """Extract token usage and cost from a LiteLLM response and accumulate.

        Writes to both in-memory stats (fast reads within same process)
        and Redis (shared across workers + API server).
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            try:
                cost = litellm_completion_cost(completion_response=response)
            except Exception:
                cost = 0.0

            # Fallback: compute from known rates if LiteLLM returned 0
            if cost == 0.0:
                pricing = _FALLBACK_PRICING.get(model)
                if pricing:
                    cost = input_tokens * pricing[0] + output_tokens * pricing[1]

            # In-memory accumulation (for local process reads)
            self.usage.record(model, input_tokens, output_tokens, cost)

            # Async Redis push — fire and forget via the event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._push_usage_to_redis(model, input_tokens, output_tokens, cost)
                )
            except RuntimeError:
                # No running event loop (e.g., during sync tests)
                pass
        except Exception as e:
            logger.debug("Failed to record usage: %s", e)

    async def _push_usage_to_redis(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> None:
        """Push usage stats to Redis so all processes share a single ledger."""
        try:
            from app.infra.redis_client import redis_client

            client = redis_client.client  # raises if not connected

            # Atomic increments on the global totals hash
            pipe = client.pipeline(transaction=False)
            pipe.hincrby(_REDIS_USAGE_KEY, "total_input_tokens", input_tokens)
            pipe.hincrby(_REDIS_USAGE_KEY, "total_output_tokens", output_tokens)
            pipe.hincrby(_REDIS_USAGE_KEY, "total_calls", 1)
            pipe.hincrbyfloat(_REDIS_USAGE_KEY, "total_cost_usd", cost)

            # Per-model hash
            model_key = f"{_REDIS_MODEL_PREFIX}{model}"
            pipe.hincrby(model_key, "calls", 1)
            pipe.hincrby(model_key, "input_tokens", input_tokens)
            pipe.hincrby(model_key, "output_tokens", output_tokens)
            pipe.hincrbyfloat(model_key, "cost_usd", cost)

            await pipe.execute()
        except Exception as e:
            logger.debug("Failed to push usage to Redis: %s", e)

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

    async def complete_for_ingestion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> ModelResponse:
        """Chat completion optimized for ingestion pipeline tasks.

        Uses the dedicated ingestion_model (default: claude-haiku-3-5) which
        has a much higher rate limit (100K tok/min) and lower cost than the
        frontier chat model — ideal for the structured JSON tasks in classify_file
        and KG extraction that run many times per ingestion job.

        Falls back to the standard fallback_model if the ingestion model fails.
        """
        return await self.complete(
            messages=messages,
            model=self.ingestion_model,
            **kwargs,
        )

    def health_check(self) -> dict[str, Any]:
        """Return LLM provider health status."""
        settings = get_settings()
        return {
            "status": "configured" if self._initialized else "not_initialized",
            "primary_model": settings.default_model,
            "fallback_model": settings.fallback_model,
            "ingestion_model": settings.ingestion_model,
            "dashscope_key_set": bool(settings.dashscope_api_key),
            "anthropic_key_set": bool(settings.anthropic_api_key),
            "openai_key_set": bool(settings.openai_api_key),
            "gemini_key_set": bool(settings.gemini_api_key),
            "openrouter_key_set": bool(settings.openrouter_api_key),
        }

    def get_cost_summary(self) -> dict[str, Any]:
        """Return accumulated token usage and estimated cost.

        Reads from in-memory stats only (synchronous).
        Use get_cost_summary_from_redis() for cross-process totals.
        """
        return {
            "total_calls": self.usage.total_calls,
            "total_input_tokens": self.usage.total_input_tokens,
            "total_output_tokens": self.usage.total_output_tokens,
            "total_tokens": self.usage.total_input_tokens + self.usage.total_output_tokens,
            "total_cost_usd": round(self.usage.total_cost_usd, 6),
            "by_model": {
                model: {
                    **stats,
                    "cost_usd": round(stats["cost_usd"], 6),
                }
                for model, stats in self.usage.by_model.items()
            },
            "note": "In-memory only — resets on server restart.",
        }

    async def get_cost_summary_from_redis(self) -> dict[str, Any]:
        """Read aggregated cost data from Redis (cross-process totals).

        This is the authoritative source — all workers push here.
        """
        try:
            from app.infra.redis_client import redis_client

            client = redis_client.client

            # Read global totals
            totals = await client.hgetall(_REDIS_USAGE_KEY)
            total_input = int(totals.get("total_input_tokens", 0))
            total_output = int(totals.get("total_output_tokens", 0))
            total_calls = int(totals.get("total_calls", 0))
            total_cost = float(totals.get("total_cost_usd", 0.0))

            # Scan for per-model keys
            by_model: dict[str, dict[str, Any]] = {}
            cursor = "0"
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor,
                    match=f"{_REDIS_MODEL_PREFIX}*",
                    count=100,
                )
                for key in keys:
                    model_name = key.replace(_REDIS_MODEL_PREFIX, "")
                    model_data = await client.hgetall(key)
                    by_model[model_name] = {
                        "calls": int(model_data.get("calls", 0)),
                        "input_tokens": int(model_data.get("input_tokens", 0)),
                        "output_tokens": int(model_data.get("output_tokens", 0)),
                        "cost_usd": round(float(model_data.get("cost_usd", 0.0)), 6),
                    }
                if cursor == "0":
                    break

            return {
                "total_calls": total_calls,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_cost_usd": round(total_cost, 6),
                "by_model": by_model,
                "source": "redis",
            }
        except Exception as e:
            logger.warning("Redis cost read failed, falling back to in-memory: %s", e)
            return self.get_cost_summary()

    def with_user_settings(
        self,
        user_settings: Any,  # UserModelSettings — using Any to avoid circular import
    ) -> ScopedLLMProvider:
        """Return a ScopedLLMProvider using the user's models and decrypted API keys."""
        from app.infra.encryption import decrypt_value

        def _safe_decrypt(enc: str | None) -> str | None:
            if enc is None:
                return None
            try:
                return decrypt_value(enc)
            except Exception:
                return None

        return ScopedLLMProvider(
            base=self,
            chat_model=user_settings.chat_model,
            ingestion_model=user_settings.ingestion_model,
            anthropic_api_key=_safe_decrypt(user_settings.anthropic_api_key_enc),
            openai_api_key=_safe_decrypt(user_settings.openai_api_key_enc),
            dashscope_api_key=_safe_decrypt(user_settings.dashscope_api_key_enc),
            openrouter_api_key=_safe_decrypt(user_settings.openrouter_api_key_enc),
        )


class ScopedLLMProvider:
    """Lightweight wrapper around LLMProvider that overrides model names
    and injects per-user API keys into LiteLLM call kwargs.

    Does NOT mutate the global llm_provider singleton.
    """

    def __init__(
        self,
        base: LLMProvider,
        chat_model: str,
        ingestion_model: str,
        anthropic_api_key: str | None = None,
        openai_api_key: str | None = None,
        dashscope_api_key: str | None = None,
        openrouter_api_key: str | None = None,
    ) -> None:
        self._base = base
        self._chat_model = chat_model
        self._ingestion_model = ingestion_model
        self._api_keys: dict[str, str] = {}
        if anthropic_api_key:
            self._api_keys["anthropic"] = anthropic_api_key
        if openai_api_key:
            self._api_keys["openai"] = openai_api_key
        if dashscope_api_key:
            self._api_keys["dashscope"] = dashscope_api_key
        if openrouter_api_key:
            self._api_keys["openrouter"] = openrouter_api_key

    def _get_api_key_for_model(self, model: str) -> str | None:
        """Return the user's API key for the given model's provider prefix."""
        if model.startswith("anthropic/"):
            return self._api_keys.get("anthropic")
        if model.startswith("openai/"):
            return self._api_keys.get("openai")
        if model.startswith("dashscope/"):
            return self._api_keys.get("dashscope")
        if model.startswith("openrouter/"):
            return self._api_keys.get("openrouter")
        return None

    @property
    def title_model(self) -> str:
        """Delegate to the base provider's title_model."""
        return self._base.title_model

    def _inject_auth(self, model: str, kwargs: dict[str, Any]) -> None:
        """Inject the appropriate auth for the model into LiteLLM kwargs."""
        api_key = self._get_api_key_for_model(model)
        if api_key:
            kwargs["api_key"] = api_key

        if model.startswith("dashscope/"):
            kwargs.setdefault("api_base", DASHSCOPE_API_BASE)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Chat completion using the user's model and API key."""
        effective_model = model or self._chat_model
        self._inject_auth(effective_model, kwargs)
        return await self._base.complete(
            messages=messages,
            model=effective_model,
            stream=stream,
            **kwargs,
        )

    async def complete_for_ingestion(
        self,
        messages: list[dict],
        **kwargs: Any,
    ) -> Any:
        """Chat completion specifically for ingestion jobs (uses ingestion_model)."""
        return await self.complete(
            messages=messages,
            model=self._ingestion_model,
            **kwargs,
        )

    async def complete_with_retry(
        self,
        messages: list[dict],
        model: str | None = None,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> Any:
        effective_model = model or self._chat_model
        self._inject_auth(effective_model, kwargs)
        return await self._base.complete_with_retry(
            messages=messages,
            model=effective_model,
            max_retries=max_retries,
            **kwargs,
        )


# Module-level singleton (initialized via lifespan)
llm_provider = LLMProvider()
