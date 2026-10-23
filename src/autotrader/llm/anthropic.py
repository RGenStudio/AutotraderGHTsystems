"""Anthropic Messages API backend (native; not OpenAI chat-completions)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from autotrader.llm.pricing import estimate_cost_usd
from autotrader.llm.providers import ANTHROPIC_API_VERSION, ANTHROPIC_MESSAGES_URL
from autotrader.llm.types import ChatMessage, LLMUsage, RawCompletion

logger = logging.getLogger(__name__)


class AnthropicMessagesBackend:
    """
    Thin HTTP wrapper around Anthropic ``POST /v1/messages``.

    Requires ``ANTHROPIC_API_KEY``. Tests should use :class:`MockLLMBackend`.
    """

    def __init__(
        self,
        *,
        api_key: str,
        url: str = ANTHROPIC_MESSAGES_URL,
        max_tokens: int = 2048,
    ) -> None:
        self.api_key = api_key
        self.url = url.rstrip("/")
        self.max_tokens = max_tokens

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_s: float,
    ) -> RawCompletion:
        system, chat = _split_system(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": 0.0,
            "messages": [{"role": m.role, "content": m.content} for m in chat],
        }
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(self.url, headers=headers, json=body)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        text = _extract_text(data)
        usage_block = data.get("usage") or {}
        tokens_in = int(usage_block.get("input_tokens") or 0)
        tokens_out = int(usage_block.get("output_tokens") or 0)
        if tokens_in <= 0:
            tokens_in = max(1, sum(len(m.content) for m in messages) // 4)
        if tokens_out <= 0:
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
                meta={"backend": "anthropic", "url": self.url},
            ),
            raw=data,
        )


def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    """Anthropic takes ``system`` separately from the messages list."""
    system_parts: list[str] = []
    chat: list[ChatMessage] = []
    for message in messages:
        if message.role == "system":
            system_parts.append(message.content)
        else:
            # Anthropic messages alternate user/assistant; map unknown → user.
            role = message.role if message.role in {"user", "assistant"} else "user"
            chat.append(ChatMessage(role=role, content=message.content))
    if not chat:
        chat = [ChatMessage(role="user", content="{}")]
    system = "\n\n".join(system_parts).strip() or None
    return system, chat


def _extract_text(data: dict[str, Any]) -> str:
    content = data.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {None, "text"} and isinstance(block.get("text"), str):
                parts.append(block["text"])
        joined = "".join(parts).strip()
        if joined:
            return joined
    raise ValueError("Anthropic response missing text content")
