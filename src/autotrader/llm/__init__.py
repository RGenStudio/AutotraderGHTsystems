"""LLMClient — sole HTTP/API boundary for model calls (mockable in CI)."""

from __future__ import annotations

from autotrader.llm.anthropic import AnthropicMessagesBackend
from autotrader.llm.client import LLMClient, LLMError, LLMResult
from autotrader.llm.credit_check import (
    ApiCreditMonitor,
    CreditCheckOutcome,
    create_api_credit_monitor,
    redact_secrets,
)
from autotrader.llm.factory import (
    create_llm_client,
    resolve_llm_backend_name,
    should_force_mock_llm,
)
from autotrader.llm.mock import MockLLMBackend
from autotrader.llm.providers import resolve_provider
from autotrader.llm.routing import RoutingLLMBackend
from autotrader.llm.types import ChatMessage, LLMUsage

__all__ = [
    "AnthropicMessagesBackend",
    "ApiCreditMonitor",
    "ChatMessage",
    "CreditCheckOutcome",
    "LLMClient",
    "LLMError",
    "LLMResult",
    "LLMUsage",
    "MockLLMBackend",
    "RoutingLLMBackend",
    "create_api_credit_monitor",
    "create_llm_client",
    "redact_secrets",
    "resolve_llm_backend_name",
    "resolve_provider",
    "should_force_mock_llm",
]
