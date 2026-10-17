"""Rough per-token USD estimates for cost journaling (mock / CI safe)."""

from __future__ import annotations

# Approximate USD per 1M tokens (input, output). Used only for journal hooks —
# not billing. Unknown models fall back to a cheap-slot estimate.
_RATES: dict[str, tuple[float, float]] = {
    "mock-cheap": (0.05, 0.20),
    "mock-mid": (0.50, 1.50),
    "mock-strong": (2.00, 8.00),
    "deepseek": (0.14, 0.28),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-haiku": (0.25, 1.25),
    "claude-sonnet": (3.00, 15.00),
}

_DEFAULT = (0.10, 0.40)


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost from token counts; never raises."""
    key = (model or "").strip().lower()
    rate_in, rate_out = _DEFAULT
    for name, rates in _RATES.items():
        if name in key:
            rate_in, rate_out = rates
            break
    return (tokens_in / 1_000_000.0) * rate_in + (tokens_out / 1_000_000.0) * rate_out
