"""Resolve which LLM provider owns a model id (brief-aligned routing)."""

from __future__ import annotations

from typing import Literal

ProviderName = Literal["openai", "deepseek", "anthropic", "mock"]

OPENAI_CHAT_BASE = "https://api.openai.com/v1"
DEEPSEEK_CHAT_BASE = "https://api.deepseek.com"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

# Env key each provider needs (documented for operators).
PROVIDER_ENV_KEYS: dict[ProviderName, str] = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mock": "",
}


def resolve_provider(model: str) -> ProviderName:
    """
    Map a model id to a provider.

    - ``claude-*`` → Anthropic Messages API
    - ``deepseek-*`` → DeepSeek OpenAI-compatible chat
    - ``mock-*`` → local mock
    - everything else (``gpt-*``, …) → OpenAI-compatible chat
    """
    key = (model or "").strip().lower()
    if not key:
        return "openai"
    if key.startswith("mock"):
        return "mock"
    if key.startswith("claude"):
        return "anthropic"
    if key.startswith("deepseek"):
        return "deepseek"
    return "openai"


def provider_env_key(provider: ProviderName) -> str:
    """Return the env var name required for ``provider`` (empty for mock)."""
    return PROVIDER_ENV_KEYS.get(provider, "")
