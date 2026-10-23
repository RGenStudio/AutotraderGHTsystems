"""LLMClient — sole HTTP/API boundary for model calls (mockable in CI)."""

from __future__ import annotations

from autotrader.llm.client import LLMClient, LLMError, LLMResult
from autotrader.llm.factory import (
    create_llm_client,
    resolve_llm_backend_name,
    should_force_mock_llm,
)
from autotrader.llm.mock import MockLLMBackend
from autotrader.llm.types import ChatMessage, LLMUsage

__all__ = [
    "ChatMessage",
    "LLMClient",
    "LLMError",
    "LLMResult",
    "LLMUsage",
    "MockLLMBackend",
    "create_llm_client",
    "resolve_llm_backend_name",
    "should_force_mock_llm",
]
