"""Risk Engine defaults and pure checks (M0 — no MT5 execution yet)."""

from __future__ import annotations

from dataclasses import dataclass

from autotrader.config import RiskLimits


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str


def default_risk_limits() -> RiskLimits:
    """Project-locked defaults: 0.5% / 2% / 5% / max open 2."""
    return RiskLimits(
        max_risk_per_trade_pct=0.5,
        max_daily_loss_pct=2.0,
        max_weekly_drawdown_pct=5.0,
        max_open_positions=2,
    )


def position_size_risk_pct(equity: float, stop_distance_price: float, risk_pct: float) -> float:
    """
    Notionals in quote units: risk amount = equity * risk_pct/100.
    Returns units such that 1R ≈ risk amount when stop_distance_price > 0.
    """
    if equity <= 0:
        raise ValueError("equity must be positive")
    if stop_distance_price <= 0:
        raise ValueError("stop_distance_price must be positive")
    if risk_pct <= 0:
        raise ValueError("risk_pct must be positive")
    risk_amount = equity * (risk_pct / 100.0)
    return risk_amount / stop_distance_price


def check_new_entry(
    *,
    limits: RiskLimits,
    open_positions: int,
    daily_loss_pct: float,
    weekly_drawdown_pct: float,
    requested_risk_pct: float,
    kill_switch: bool = False,
) -> RiskDecision:
    """Pure gate for a new entry — used by later Risk Engine wiring."""
    if kill_switch:
        return RiskDecision(False, "kill_switch_active")
    if open_positions >= limits.max_open_positions:
        return RiskDecision(False, "max_open_positions")
    if daily_loss_pct >= limits.max_daily_loss_pct:
        return RiskDecision(False, "max_daily_loss")
    if weekly_drawdown_pct >= limits.max_weekly_drawdown_pct:
        return RiskDecision(False, "max_weekly_drawdown")
    if requested_risk_pct > limits.max_risk_per_trade_pct:
        return RiskDecision(False, "requested_risk_above_cap")
    return RiskDecision(True, "ok")
