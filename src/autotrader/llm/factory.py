"""Build an LLMClient — mock by default (CI / no API keys)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from autotrader.config import EnvSettings, load_config
from autotrader.llm.client import CostHook, LLMClient
from autotrader.llm.http import HttpxLLMBackend
from autotrader.llm.mock import MockLLMBackend
from autotrader.llm.types import LLMUsage

# re-export for typing convenience
__all__ = [
    "create_llm_client",
    "journal_cost_hook",
    "make_recording_cost_hook",
]

logger = logging.getLogger(__name__)


def create_llm_client(
    *,
    env: EnvSettings | None = None,
    force_mock: bool = False,
    cost_hook: CostHook | None = None,
    mock_backend: MockLLMBackend | None = None,
    timeout_s: float | None = None,
) -> LLMClient:
    """
    Prefer mock unless explicitly configured for HTTP and keys are present.

    Linux CI and paper smoke always work without API keys when
    ``llm.backend`` is ``mock`` (default) or ``force_mock=True``.
    """
    settings = env or EnvSettings()
    cfg = load_config()
    backend_name = str(cfg.llm.backend).lower()
    cfg_timeout = float(cfg.llm.timeout_seconds)

    timeout = float(timeout_s if timeout_s is not None else cfg_timeout)
    # Env override for tests / ops
    if os.environ.get("LLM_BACKEND", "").strip().lower() == "mock":
        force_mock = True

    if force_mock or backend_name == "mock":
        backend = mock_backend or MockLLMBackend()
        logger.info("Using mock LLM backend")
        return LLMClient(backend, timeout_s=timeout, cost_hook=cost_hook)

    base_url = (settings.llm_base_url or "").strip()
    api_key = _first_api_key(settings)
    if not base_url or not api_key:
        logger.info(
            "LLM HTTP requested but base URL/key missing — falling back to mock"
        )
        return LLMClient(
            mock_backend or MockLLMBackend(),
            timeout_s=timeout,
            cost_hook=cost_hook,
        )

    logger.info("Using HTTP LLM backend base_url=%s", base_url)
    return LLMClient(
        HttpxLLMBackend(base_url=base_url, api_key=api_key),
        timeout_s=timeout,
        cost_hook=cost_hook,
    )


def journal_cost_hook(journal: Any) -> CostHook:
    """
    Build a cost hook that writes ``costs`` rows (kind=llm_api).

    Returns the new cost row id when possible. Agent-call linking is done by
    callers that already have an ``agent_call_id``.
    """

    def _hook(usage: LLMUsage, agent_name: str, agent_call_id: int | None) -> int | None:
        if usage.cost_usd <= 0 and usage.tokens_in <= 0 and usage.tokens_out <= 0:
            return None
        return journal.record_cost(
            kind="llm_api",
            amount=float(usage.cost_usd),
            currency="USD",
            agent_call_id=agent_call_id,
            meta={
                "agent_name": agent_name,
                "model": usage.model,
                "tokens_in": usage.tokens_in,
                "tokens_out": usage.tokens_out,
                "latency_ms": usage.latency_ms,
            },
        )

    return _hook


def make_recording_cost_hook(
    sink: list[tuple[LLMUsage, str]],
) -> CostHook:
    """Tiny test helper — append usage tuples; returns None."""

    def _hook(usage: LLMUsage, agent_name: str, agent_call_id: int | None) -> None:
        _ = agent_call_id
        sink.append((usage, agent_name))

    return _hook


def _first_api_key(settings: EnvSettings) -> str:
    for value in (
        settings.openai_api_key,
        settings.anthropic_api_key,
        settings.deepseek_api_key,
    ):
        if value and str(value).strip():
            return str(value).strip()
    return ""


# typing aid for callers that want an explicit Callable
CostHookFactory = Callable[[Any], CostHook]
