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
    "resolve_llm_backend_name",
    "should_force_mock_llm",
]

logger = logging.getLogger(__name__)


def resolve_llm_backend_name(
    *,
    config_backend: str | None = None,
    env: EnvSettings | None = None,
) -> str:
    """
    Resolve ``mock`` vs ``http``.

    Precedence: ``LLM_BACKEND`` env (``mock``|``http``) → YAML ``llm.backend``
    → default ``http``. Empty / whitespace env is treated as unset.
    """
    settings = env or EnvSettings()
    raw = settings.llm_backend if settings.llm_backend is not None else os.environ.get(
        "LLM_BACKEND", ""
    )
    env_backend = (raw or "").strip().lower()
    if env_backend in {"mock", "http"}:
        return env_backend
    name = (config_backend if config_backend is not None else load_config().llm.backend)
    return str(name).strip().lower() or "http"


def should_force_mock_llm(*, config_backend: str | None = None) -> bool:
    """True when CLI/orchestrator should keep the mock backend (CI-safe default)."""
    return resolve_llm_backend_name(config_backend=config_backend) != "http"


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
    backend_name = resolve_llm_backend_name(
        config_backend=cfg.llm.backend, env=settings
    )
    cfg_timeout = float(cfg.llm.timeout_seconds)

    timeout = float(timeout_s if timeout_s is not None else cfg_timeout)
    # Env override for tests / ops — LLM_BACKEND=mock always wins.
    if (settings.llm_backend or os.environ.get("LLM_BACKEND", "")).strip().lower() == (
        "mock"
    ):
        force_mock = True

    if force_mock or backend_name == "mock":
        backend = mock_backend or MockLLMBackend()
        logger.info("Using mock LLM backend")
        return LLMClient(backend, timeout_s=timeout, cost_hook=cost_hook)

    base_url = _resolve_base_url(settings)
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


def _resolve_base_url(settings: EnvSettings) -> str:
    """
    Prefer ``LLM_BASE_URL``; otherwise infer a common OpenAI-compatible host.

    Anthropic's native Messages API is not OpenAI chat-completions compatible —
    leave ``LLM_BASE_URL`` set to a compatible gateway if using Anthropic keys.
    """
    explicit = (settings.llm_base_url or "").strip()
    if explicit:
        return explicit
    if settings.openai_api_key and str(settings.openai_api_key).strip():
        return "https://api.openai.com/v1"
    if settings.deepseek_api_key and str(settings.deepseek_api_key).strip():
        return "https://api.deepseek.com"
    return ""


# typing aid for callers that want an explicit Callable
CostHookFactory = Callable[[Any], CostHook]
