"""Risk Engine — code authority over candidate orders (paper/demo phase)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from autotrader.active_window import is_within_active_window
from autotrader.config import ActiveWindow, Mode, RiskLimits
from autotrader.kill_switch import KillSwitch

_UNSET: object = object()


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str


class DecisionPayload(BaseModel):
    """
    Schema for a Decision Maker-style JSON payload (pre-LLM wiring).

    Invalid / missing required fields → Risk Engine rejects (bad JSON ≡ reject).
    """

    action: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    side: str = Field(..., min_length=1)
    requested_risk_pct: float = Field(..., gt=0)
    stop_distance_price: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)

    @field_validator("action")
    @classmethod
    def _action_enter_or_skip(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"enter", "skip"}:
            raise ValueError("action must be 'enter' or 'skip'")
        return normalized

    @field_validator("side")
    @classmethod
    def _side_long_or_short(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"long", "short", "buy", "sell"}:
            raise ValueError("side must be long/short (or buy/sell)")
        return "long" if normalized in {"long", "buy"} else "short"

    @field_validator("symbol")
    @classmethod
    def _symbol_upper(cls, value: str) -> str:
        return value.strip().upper()


@dataclass(frozen=True, slots=True)
class CandidateOrder:
    """Normalized candidate entry presented to the Risk Engine."""

    symbol: str
    side: str  # long | short
    requested_risk_pct: float
    stop_distance_price: float
    entry_price: float
    idempotency_key: str
    raw_decision: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OpenPositionView:
    """Minimal open-position view for risk checks (local or broker stub)."""

    symbol: str
    side: str = "long"
    ticket: str = ""


@dataclass(frozen=True, slots=True)
class RiskContext:
    """Portfolio / clock state evaluated every cycle with the candidate."""

    equity: float
    open_positions: tuple[OpenPositionView, ...] = ()
    daily_loss_pct: float = 0.0
    weekly_drawdown_pct: float = 0.0
    now: datetime | None = None
    mode: Mode = Mode.PAPER


@dataclass
class RiskEngine:
    """
    Code authority: approve or reject candidate orders before execution.

    AI / Decision Maker output cannot raise these ceilings. Every cycle must
    consult the kill switch and active window before allowing a new entry.
    """

    limits: RiskLimits
    active_window: ActiveWindow = field(default_factory=ActiveWindow)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    allowed_symbols: tuple[str, ...] = ("EURUSD", "USDJPY")
    allow_live: bool = False  # hard off for this phase; tests must not flip casually

    def check_kill_switch(self) -> bool:
        """Every-cycle kill-switch probe (True = blocked)."""
        return self.kill_switch.check()

    def evaluate(
        self,
        candidate: CandidateOrder | None,
        context: RiskContext,
        *,
        raw_json: Any = _UNSET,
    ) -> RiskDecision:
        """
        Approve or reject a candidate entry.

        ``raw_json`` (optional) is validated as DecisionPayload when provided;
        malformed / non-dict / ``None`` payloads are rejected as ``bad_json``.
        Passing ``candidate=None`` with valid ``raw_json`` builds the candidate
        from the payload (action ``skip`` → reject with ``decision_skip``).
        """
        if self.check_kill_switch():
            return RiskDecision(False, "kill_switch_active")

        if context.mode == Mode.LIVE and not self.allow_live:
            return RiskDecision(False, "live_mode_forbidden")

        if raw_json is not _UNSET:
            parsed = self._parse_decision_json(raw_json)
            if isinstance(parsed, RiskDecision):
                return parsed
            if parsed.action == "skip":
                return RiskDecision(False, "decision_skip")
            candidate = CandidateOrder(
                symbol=parsed.symbol,
                side=parsed.side,
                requested_risk_pct=parsed.requested_risk_pct,
                stop_distance_price=parsed.stop_distance_price,
                entry_price=parsed.entry_price,
                idempotency_key=parsed.idempotency_key,
                raw_decision=raw_json if isinstance(raw_json, dict) else None,
            )

        if candidate is None:
            return RiskDecision(False, "missing_candidate")

        if not candidate.idempotency_key.strip():
            return RiskDecision(False, "missing_idempotency_key")

        symbol = candidate.symbol.strip().upper()
        if symbol not in {s.upper() for s in self.allowed_symbols}:
            return RiskDecision(False, "symbol_not_allowed")

        if context.now is not None and not is_within_active_window(
            context.now, self.active_window
        ):
            return RiskDecision(False, "outside_active_window")

        open_count = len(context.open_positions)
        if open_count >= self.limits.max_open_positions:
            return RiskDecision(False, "max_open_positions")

        open_symbols = {p.symbol.strip().upper() for p in context.open_positions}
        if symbol in open_symbols:
            return RiskDecision(False, "symbol_already_open")

        if context.daily_loss_pct >= self.limits.max_daily_loss_pct:
            return RiskDecision(False, "max_daily_loss")

        if context.weekly_drawdown_pct >= self.limits.max_weekly_drawdown_pct:
            # Weekly DD engages kill switch until human review
            self.kill_switch.engage("max_weekly_drawdown")
            return RiskDecision(False, "max_weekly_drawdown")

        if candidate.requested_risk_pct > self.limits.max_risk_per_trade_pct:
            return RiskDecision(False, "requested_risk_above_cap")

        if candidate.requested_risk_pct <= 0:
            return RiskDecision(False, "requested_risk_invalid")

        if candidate.stop_distance_price <= 0 or candidate.entry_price <= 0:
            return RiskDecision(False, "invalid_prices")

        if context.equity <= 0:
            return RiskDecision(False, "invalid_equity")

        return RiskDecision(True, "ok")

    @staticmethod
    def _parse_decision_json(raw: Any) -> DecisionPayload | RiskDecision:
        if not isinstance(raw, dict):
            return RiskDecision(False, "bad_json")
        try:
            return DecisionPayload.model_validate(raw)
        except ValidationError:
            return RiskDecision(False, "bad_json")


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
    """
    Pure gate for a new entry (M0 compatibility).

    Prefer :class:`RiskEngine` for active window, JSON validation, and
    one-per-symbol checks.
    """
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
