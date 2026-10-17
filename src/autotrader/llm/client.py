"""LLMClient — HTTP wrapper with pydantic validation, timeout, and cost hooks."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from autotrader.llm.types import ChatMessage, LLMUsage, RawCompletion

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

CostHook = Callable[[LLMUsage, str, int | None], None]
"""(usage, agent_name, agent_call_id) → journal/costs side effect."""


class LLMBackend(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_s: float,
    ) -> RawCompletion: ...


class LLMError(Exception):
    """Raised only when callers opt into strict mode; soft failures use LLMResult."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


@dataclass(frozen=True, slots=True)
class LLMResult(Generic[T]):
    """Validated completion or a soft failure (bad JSON / timeout / transport)."""

    success: bool
    parsed: T | None
    raw_text: str
    usage: LLMUsage
    error: str = ""
    agent_call_id: int | None = None

    @property
    def should_trade(self) -> bool:
        """Hard rule: schema/LLM failure ⇒ do not trade."""
        return self.success and self.parsed is not None


class LLMClient:
    """
    Sole entry point for model calls.

    - Validates assistant JSON against a pydantic ``schema``.
    - Enforces ``timeout_s`` at the backend boundary.
    - Optionally records costs via ``cost_hook`` (journal ``costs`` / ``agent_calls``).
    - Never logs API keys.
    """

    def __init__(
        self,
        backend: LLMBackend,
        *,
        timeout_s: float = 30.0,
        cost_hook: CostHook | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._backend = backend
        self.timeout_s = timeout_s
        self.cost_hook = cost_hook

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage] | list[dict[str, str]],
        schema: type[T],
        agent_name: str = "",
        system: str | None = None,
    ) -> LLMResult[T]:
        """
        Call the backend and validate JSON into ``schema``.

        On timeout, transport error, invalid JSON, or ValidationError: returns
        ``success=False`` with ``parsed=None`` (caller must not trade).
        """
        normalized = _normalize_messages(messages, system=system)
        try:
            raw = self._backend.complete(
                model=model,
                messages=normalized,
                timeout_s=self.timeout_s,
            )
        except TimeoutError as exc:
            return self._fail(
                model=model,
                agent_name=agent_name,
                error=f"timeout: {exc}",
                usage=LLMUsage(model=model),
            )
        except Exception as exc:  # noqa: BLE001 — soft-fail boundary
            logger.warning("LLM backend failed agent=%s model=%s: %s", agent_name, model, exc)
            return self._fail(
                model=model,
                agent_name=agent_name,
                error=f"llm_error: {exc}",
                usage=LLMUsage(model=model),
            )

        return self._parse_and_hook(
            raw=raw,
            schema=schema,
            agent_name=agent_name,
        )

    def _parse_and_hook(
        self,
        *,
        raw: RawCompletion,
        schema: type[T],
        agent_name: str,
    ) -> LLMResult[T]:
        text = (raw.text or "").strip()
        if not text:
            return self._fail(
                model=raw.usage.model,
                agent_name=agent_name,
                error="empty_response",
                usage=raw.usage,
                raw_text=text,
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return self._fail(
                model=raw.usage.model,
                agent_name=agent_name,
                error=f"bad_json: {exc}",
                usage=raw.usage,
                raw_text=text,
            )
        try:
            parsed = schema.model_validate(data)
        except ValidationError as exc:
            return self._fail(
                model=raw.usage.model,
                agent_name=agent_name,
                error=f"schema_invalid: {exc.error_count()} errors",
                usage=raw.usage,
                raw_text=text,
            )

        agent_call_id = self._invoke_cost_hook(raw.usage, agent_name)
        return LLMResult(
            success=True,
            parsed=parsed,
            raw_text=text,
            usage=raw.usage,
            agent_call_id=agent_call_id,
        )

    def _fail(
        self,
        *,
        model: str,
        agent_name: str,
        error: str,
        usage: LLMUsage,
        raw_text: str = "",
    ) -> LLMResult[Any]:
        # Still record cost/latency attempt when usage carries tokens
        agent_call_id = self._invoke_cost_hook(usage, agent_name)
        return LLMResult(
            success=False,
            parsed=None,
            raw_text=raw_text,
            usage=usage if usage.model else LLMUsage(model=model),
            error=error,
            agent_call_id=agent_call_id,
        )

    def _invoke_cost_hook(self, usage: LLMUsage, agent_name: str) -> int | None:
        if self.cost_hook is None:
            return None
        try:
            result = self.cost_hook(usage, agent_name, None)
            return int(result) if isinstance(result, int) else None
        except Exception:  # noqa: BLE001 — journal must not break trading gate
            logger.exception("LLM cost_hook failed agent=%s", agent_name)
            return None


def _normalize_messages(
    messages: list[ChatMessage] | list[dict[str, str]],
    *,
    system: str | None,
) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    if system:
        out.append(ChatMessage(role="system", content=system))
    for item in messages:
        if isinstance(item, ChatMessage):
            out.append(item)
        else:
            out.append(ChatMessage(role=str(item["role"]), content=str(item["content"])))
    return out
