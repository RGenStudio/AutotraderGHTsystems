"""ORM tables for the trade journal (brief M4 schema)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for AutoTrader tables."""


class SignalRow(Base):
    """Strategy Engine candidate signal (code-only; no AI)."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bar_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    decisions: Mapped[list[DecisionRow]] = relationship(back_populates="signal")


class DecisionRow(Base):
    """Every Risk Engine / Decision Maker outcome with reason."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", index=True
    )
    candidate_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    config_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("signals.id"), nullable=True, index=True
    )

    signal: Mapped[SignalRow | None] = relationship(back_populates="decisions")
    orders: Mapped[list[OrderRow]] = relationship(back_populates="decision")
    agent_calls: Mapped[list[AgentCallRow]] = relationship(back_populates="decision")


class AgentCallRow(Base):
    """
    LLM / agent call log (schema ready for M5; unused until agents ship).

    Stores input/output, prompt version, token counts, and estimated cost.
    """

    __tablename__ = "agent_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("decisions.id"), nullable=True, index=True
    )

    decision: Mapped[DecisionRow | None] = relationship(back_populates="agent_calls")
    costs: Mapped[list[CostRow]] = relationship(back_populates="agent_call")


class OrderRow(Base):
    """Approved / sent order + execution outcome (paper or stub)."""

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("decisions.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    risk_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ticket: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    execution_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    decision: Mapped[DecisionRow | None] = relationship(back_populates="orders")
    trades: Mapped[list[TradeRow]] = relationship(back_populates="order")


class TradeRow(Base):
    """Open or closed trade linked to an order."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    ticket: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[OrderRow | None] = relationship(back_populates="trades")
    costs: Mapped[list[CostRow]] = relationship(back_populates="trade")


class CostRow(Base):
    """Spread / slippage / fee / LLM API cost line items."""

    __tablename__ = "costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("trades.id"), nullable=True, index=True
    )
    agent_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_calls.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    trade: Mapped[TradeRow | None] = relationship(back_populates="costs")
    agent_call: Mapped[AgentCallRow | None] = relationship(back_populates="costs")


class SystemEventRow(Base):
    """Engine heartbeat, reconcile, kill-switch, and other system events."""

    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class KillSwitchStateRow(Base):
    """Singleton kill-switch persistence (id always 1)."""

    __tablename__ = "kill_switch_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    engaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
