"""OpenAI-compatible HTTP chat-completions backend (optional; not used in CI)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from autotrader.llm.pricing import estimate_cost_usd
from autotrader.llm.types import ChatMessage, LLMUsage, RawCompletion

logger = logging.getLogger(__name__)


class HttpxLLMBackend:
    """
    Thin HTTP wrapper around an OpenAI-compatible ``/chat/completions`` endpoint.

    Requires a base URL + API key from env. Tests should use :class:`MockLLMBackend`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        path: str = "/chat/completions",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.path = path if path.startswith("/") else f"/{path}"

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_s: float,
    ) -> RawCompletion:
        url = f"{self.base_url}{self.path}"
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        text = _extract_text(data)
        usage_block = data.get("usage") or {}
        tokens_in = int(usage_block.get("prompt_tokens") or usage_block.get("input_tokens") or 0)
        tokens_out = int(
            usage_block.get("completion_tokens") or usage_block.get("output_tokens") or 0
        )
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
                meta={"backend": "http", "url": url},
            ),
            raw=data,
        )


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        # Some providers return content at top level
        content = data.get("content") or data.get("output_text")
        if isinstance(content, str):
            return content
        raise ValueError("LLM response missing choices/content")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {None, "text", "output_text"}
        ]
        joined = "".join(parts).strip()
        if joined:
            return joined
    # Fallback: dump whole message for debugging (still validated upstream)
    return json.dumps(message)
