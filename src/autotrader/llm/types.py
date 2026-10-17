"""Shared LLM request/response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Token counts and estimated USD cost for one completion."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""
    latency_ms: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawCompletion:
    """Backend-level text completion before schema validation."""

    text: str
    usage: LLMUsage
    raw: dict[str, Any] | None = None
