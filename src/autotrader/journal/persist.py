"""Helpers to persist M3 risk / execution outcomes into the trade journal."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from autotrader.execution.types import ApprovedOrder, ExecutionResult, ExecutionStatus
from autotrader.journal.api import TradeJournal
from autotrader.risk import CandidateOrder, RiskContext, RiskDecision
from autotrader.strategy.types import Signal


def _dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def persist_signal(
    journal: TradeJournal,
    signal: Signal,
    *,
    symbol: str,
    created_at: datetime | None = None,
) -> int:
    """Write a Strategy Engine :class:`~autotrader.strategy.types.Signal`."""
    payload = {
        "strategy": signal.strategy.value if hasattr(signal.strategy, "value") else str(signal.strategy),
        "side": signal.side.value if hasattr(signal.side, "value") else str(signal.side),
        "bar_index": signal.bar_index,
        "bar_time": signal.bar_time.isoformat(),
        "entry_price": signal.entry_price,
        "stop_price": signal.stop_price,
        "take_profit": signal.take_profit,
        "atr": signal.atr,
        "reason": signal.reason,
        "trail_atr_mult": signal.trail_atr_mult,
        "max_bars": signal.max_bars,
        "exit_mid_band": signal.exit_mid_band,
    }
    return journal.record_signal(
        symbol=symbol,
        strategy=str(payload["strategy"]),
        side=str(payload["side"]),
        bar_time=signal.bar_time,
        bar_index=signal.bar_index,
        entry_price=signal.entry_price,
        stop_price=signal.stop_price,
        take_profit=signal.take_profit,
        atr=signal.atr,
        reason=signal.reason,
        payload=payload,
        created_at=created_at,
    )


def persist_risk_outcome(
    journal: TradeJournal,
    decision: RiskDecision,
    *,
    candidate: CandidateOrder | None = None,
    context: RiskContext | None = None,
    config_snapshot: dict[str, Any] | None = None,
    signal_id: int | None = None,
    created_at: datetime | None = None,
) -> int:
    """
    Persist a :class:`~autotrader.risk.RiskDecision` with candidate + context.

    Always records ``reason`` so every approve/reject is auditable.
    """
    candidate_json: dict[str, Any] | None = None
    symbol: str | None = None
    action = "enter" if decision.allowed else "reject"
    idempotency_key = ""
    if candidate is not None:
        symbol = candidate.symbol
        idempotency_key = candidate.idempotency_key
        candidate_json = {
            "symbol": candidate.symbol,
            "side": candidate.side,
            "requested_risk_pct": candidate.requested_risk_pct,
            "stop_distance_price": candidate.stop_distance_price,
            "entry_price": candidate.entry_price,
            "idempotency_key": candidate.idempotency_key,
            "raw_decision": candidate.raw_decision,
        }
        if not decision.allowed and decision.reason == "decision_skip":
            action = "skip"

    context_json: dict[str, Any] | None = None
    if context is not None:
        context_json = {
            "equity": context.equity,
            "daily_loss_pct": context.daily_loss_pct,
            "weekly_drawdown_pct": context.weekly_drawdown_pct,
            "mode": context.mode.value if hasattr(context.mode, "value") else str(context.mode),
            "now": context.now.isoformat() if context.now else None,
            "open_positions": [
                {"symbol": p.symbol, "side": p.side, "ticket": p.ticket}
                for p in context.open_positions
            ],
        }

    return journal.record_decision(
        allowed=decision.allowed,
        reason=decision.reason,
        symbol=symbol,
        action=action,
        idempotency_key=idempotency_key,
        candidate=candidate_json,
        context=context_json,
        config_snapshot=config_snapshot,
        signal_id=signal_id,
        created_at=created_at,
    )


def persist_execution_outcome(
    journal: TradeJournal,
    order: ApprovedOrder,
    result: ExecutionResult,
    *,
    decision_id: int | None = None,
    created_at: datetime | None = None,
    open_trade: bool = True,
) -> tuple[int, int | None]:
    """
    Persist an approved order + execution result; optionally open a trade row.

    Returns ``(order_id, trade_id_or_None)``.
    """
    execution = {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "ticket": result.ticket,
        "message": result.message,
        "idempotency_key": result.idempotency_key or order.idempotency_key,
    }
    order_id = journal.record_order(
        decision_id=decision_id,
        symbol=order.symbol,
        side=order.side,
        volume=order.volume,
        entry_price=order.entry_price,
        stop_price=order.stop_price,
        take_profit=order.take_profit,
        idempotency_key=order.idempotency_key,
        risk_pct=order.risk_pct,
        status=str(execution["status"]),
        ticket=result.ticket,
        message=result.message,
        execution=execution,
        created_at=created_at,
    )
    trade_id: int | None = None
    if open_trade and result.status == ExecutionStatus.FILLED:
        trade_id = journal.record_trade(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            volume=order.volume,
            entry_price=order.entry_price,
            stop_price=order.stop_price,
            take_profit=order.take_profit,
            ticket=result.ticket,
            status="open",
            opened_at=_dt(created_at) or datetime.now(UTC),
            created_at=created_at,
        )
    return order_id, trade_id
