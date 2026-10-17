"""Scripted LLM backend for CI — no network, no API keys."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from autotrader.llm.pricing import estimate_cost_usd
from autotrader.llm.types import ChatMessage, LLMUsage, RawCompletion

Responder = Callable[[str, list[ChatMessage]], str | dict[str, Any]]


@dataclass
class MockLLMBackend:
    """
    In-memory completions keyed by model name or a custom responder.

    Default responses are valid JSON objects so agents can validate schemas
    unless a test injects malformed text via ``queue`` / ``responder``.
    """

    responses_by_model: dict[str, str | dict[str, Any]] = field(default_factory=dict)
    queue: list[str | dict[str, Any] | BaseException] = field(default_factory=list)
    responder: Responder | None = None
    default_response: dict[str, Any] = field(
        default_factory=lambda: {"ok": True, "reasoning": "mock default"}
    )
    latency_ms: int = 1
    fail_with: BaseException | None = None
    call_count: int = 0
    last_messages: list[ChatMessage] = field(default_factory=list)
    last_model: str = ""

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_s: float,
    ) -> RawCompletion:
        _ = timeout_s
        self.call_count += 1
        self.last_model = model
        self.last_messages = list(messages)

        if self.fail_with is not None:
            raise self.fail_with

        started = time.perf_counter()
        payload = self._resolve_payload(model, messages)
        if isinstance(payload, BaseException):
            raise payload

        text = payload if isinstance(payload, str) else json.dumps(payload)
        elapsed_ms = max(self.latency_ms, int((time.perf_counter() - started) * 1000))
        tokens_in = max(1, sum(len(m.content) for m in messages) // 4)
        tokens_out = max(1, len(text) // 4)
        cost = estimate_cost_usd(model, tokens_in, tokens_out)
        return RawCompletion(
            text=text,
            usage=LLMUsage(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                model=model,
                latency_ms=elapsed_ms,
                meta={"backend": "mock"},
            ),
            raw={"mock": True, "model": model},
        )

    def _resolve_payload(
        self, model: str, messages: list[ChatMessage]
    ) -> str | dict[str, Any] | BaseException:
        if self.queue:
            return self.queue.pop(0)
        if self.responder is not None:
            return self.responder(model, messages)
        if model in self.responses_by_model:
            return self.responses_by_model[model]
        # Match partial model keys (e.g. "cheap" in "mock-cheap-technical")
        for key, value in self.responses_by_model.items():
            if key and key in model:
                return value
        return dict(self.default_response)

    def enqueue(self, *items: str | dict[str, Any] | BaseException) -> None:
        self.queue.extend(items)

    def set_response(self, model: str, payload: str | Mapping[str, Any]) -> None:
        self.responses_by_model[model] = (
            dict(payload) if isinstance(payload, Mapping) else payload
        )
