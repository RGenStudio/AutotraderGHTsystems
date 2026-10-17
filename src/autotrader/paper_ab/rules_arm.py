"""Rules-only arm helpers — Strategy Engine signal → Risk Engine payload (no LLM)."""

from __future__ import annotations

from typing import Any

from autotrader.paper_ab.scenarios import SyntheticCycle


def rules_only_risk_payload(
    cycle: SyntheticCycle,
    *,
    idempotency_key: str,
    max_risk_pct: float = 0.5,
) -> dict[str, Any]:
    """
    Build a Risk Engine enter payload directly from the strategy signal.

    No Agents 1–4; AI cannot invent or alter the signal. Risk % is capped at
    the project ceiling (default 0.5%).
    """
    if not cycle.has_signal:
        raise ValueError("cycle has no signal")
    stop_distance = abs(cycle.entry_price - cycle.stop_price)
    if stop_distance <= 0:
        raise ValueError("stop_distance must be > 0")
    risk_pct = min(float(cycle.risk_pct), float(max_risk_pct))
    return {
        "action": "enter",
        "symbol": cycle.symbol.upper(),
        "side": cycle.side.lower(),
        "requested_risk_pct": risk_pct,
        "stop_distance_price": stop_distance,
        "entry_price": float(cycle.entry_price),
        "idempotency_key": idempotency_key,
        "stop_loss": float(cycle.stop_price),
        "take_profit": float(cycle.take_profit) if cycle.take_profit is not None else None,
        "confidence": 100,
        "reasoning": f"rules_only strategy={cycle.strategy}",
        "conflicts_noted": [],
        "arm": "rules_only",
    }


def ai_scripted_decision(
    cycle: SyntheticCycle,
    *,
    idempotency_key: str,
    max_risk_pct: float = 0.5,
) -> tuple[str, dict[str, Any] | None]:
    """
    Simulate Agent 4 outcome for mock cycles without network LLM calls.

    Returns ``(reason, risk_payload_or_none)``.
    Reasons mirror the live pipeline: ``ok`` | ``decision_skip`` | ``bad_json`` |
    ``llm_or_schema_fail``.
    """
    if not cycle.has_signal:
        return "no_signal", None

    if cycle.ai_outcome == "bad_json":
        return "bad_json", None
    if cycle.ai_outcome == "llm_fail":
        return "llm_or_schema_fail", None
    if cycle.ai_outcome == "skip":
        return "decision_skip", {
            "action": "skip",
            "symbol": cycle.symbol.upper(),
            "side": cycle.side.lower(),
            "requested_risk_pct": 0.01,
            "stop_distance_price": 0.0001,
            "entry_price": float(cycle.entry_price),
            "idempotency_key": idempotency_key or "skip",
            "confidence": 40,
            "reasoning": "rules_plus_ai scripted skip",
            "conflicts_noted": [],
            "arm": "rules_plus_ai",
        }

    # enter — optionally slightly more selective sizing still within ceiling
    stop_distance = abs(cycle.entry_price - cycle.stop_price)
    risk_pct = min(float(cycle.risk_pct), float(max_risk_pct))
    return "ok", {
        "action": "enter",
        "symbol": cycle.symbol.upper(),
        "side": cycle.side.lower(),
        "requested_risk_pct": risk_pct,
        "stop_distance_price": stop_distance,
        "entry_price": float(cycle.entry_price),
        "idempotency_key": idempotency_key,
        "stop_loss": float(cycle.stop_price),
        "take_profit": float(cycle.take_profit) if cycle.take_profit is not None else None,
        "confidence": 75,
        "reasoning": f"rules_plus_ai strategy={cycle.strategy}",
        "conflicts_noted": [],
        "arm": "rules_plus_ai",
    }
