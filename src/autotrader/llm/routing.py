"""Per-model provider routing with soft mock fallback when a key is missing."""

from __future__ import annotations

import logging
from typing import Any

from autotrader.config import EnvSettings
from autotrader.llm.anthropic import AnthropicMessagesBackend
from autotrader.llm.http import HttpxLLMBackend
from autotrader.llm.mock import MockLLMBackend
from autotrader.llm.providers import (
    DEEPSEEK_CHAT_BASE,
    OPENAI_CHAT_BASE,
    ProviderName,
    provider_env_key,
    resolve_provider,
)
from autotrader.llm.types import ChatMessage, RawCompletion

logger = logging.getLogger(__name__)


class RoutingLLMBackend:
    """
    Route each completion to OpenAI / DeepSeek / Anthropic by model id.

    Missing provider key → soft-fallback to :class:`MockLLMBackend` for that
    call only (orchestrator loop must not crash). Never logs API keys.
    """

    def __init__(
        self,
        *,
        env: EnvSettings,
        mock_backend: MockLLMBackend | None = None,
    ) -> None:
        self._env = env
        self._mock = mock_backend or MockLLMBackend()
        self._backends: dict[ProviderName, Any] = {}
        self._build_backends()

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_s: float,
    ) -> RawCompletion:
        provider = resolve_provider(model)
        backend = self._backends.get(provider)
        if backend is None:
            env_name = provider_env_key(provider) or "(none)"
            logger.warning(
                "LLM provider=%s model=%s missing %s — soft-fallback to mock",
                provider,
                model,
                env_name,
            )
            backend = self._mock
        return backend.complete(model=model, messages=messages, timeout_s=timeout_s)

    def _build_backends(self) -> None:
        openai_key = _strip(self._env.openai_api_key)
        deepseek_key = _strip(self._env.deepseek_api_key)
        anthropic_key = _strip(self._env.anthropic_api_key)
        explicit_base = _strip(self._env.llm_base_url)

        if openai_key:
            openai_base = explicit_base or OPENAI_CHAT_BASE
            self._backends["openai"] = HttpxLLMBackend(
                base_url=openai_base, api_key=openai_key
            )
            logger.info("LLM route openai → %s", openai_base)

        if deepseek_key:
            # DeepSeek keeps its own host even when LLM_BASE_URL is set for OpenAI.
            self._backends["deepseek"] = HttpxLLMBackend(
                base_url=DEEPSEEK_CHAT_BASE, api_key=deepseek_key
            )
            logger.info("LLM route deepseek → %s", DEEPSEEK_CHAT_BASE)

        if anthropic_key:
            self._backends["anthropic"] = AnthropicMessagesBackend(api_key=anthropic_key)
            logger.info("LLM route anthropic → Messages API")

        # Always available for mock-* model ids and soft-fallback.
        self._backends["mock"] = self._mock

        if not any(
            name in self._backends for name in ("openai", "deepseek", "anthropic")
        ):
            logger.info(
                "LLM HTTP requested but no provider keys set — all models soft-mock"
            )


def _strip(value: str | None) -> str:
    return str(value).strip() if value else ""
