"""Trade Journal API: record decisions with reasons; query by time/symbol."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, Select, select
from sqlalchemy.orm import Session

from autotrader.db.engine import (
    create_db_engine,
    init_db,
    make_session_factory,
    resolve_database_url,
)
from autotrader.db.models import (
    AgentCallRow,
    CostRow,
    DecisionRow,
    KillSwitchStateRow,
    OrderRow,
    SignalRow,
    SystemEventRow,
    TradeRow,
)
from autotrader.kill_switch import KillSwitchState

KILL_SWITCH_ROW_ID = 1


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class TradeJournal:
    """
    Persist and query journal tables (signals, decisions, orders, trades, …).

    Designed for paper/demo: no secrets stored. Use a temp SQLite file in tests.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        database_url: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.database_url = database_url
        self._engine = engine

    def dispose(self) -> None:
        """Drop pooled connections so the next cycle dials again after an outage."""
        if self._engine is not None:
            self._engine.dispose()

    # --- writers -------------------------------------------------------------

    def record_signal(
        self,
        *,
        symbol: str,
        strategy: str,
        side: str,
        bar_time: datetime,
        entry_price: float,
        stop_price: float,
        atr: float = 0.0,
        bar_index: int = 0,
        take_profit: float | None = None,
        reason: str = "",
        payload: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> int:
        row = SignalRow(
            created_at=created_at or _utc_now(),
            symbol=symbol.strip().upper(),
            strategy=str(strategy),
            side=str(side).lower(),
            bar_time=_ensure_aware(bar_time),
            bar_index=bar_index,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit=take_profit,
            atr=atr,
            reason=reason,
            payload_json=payload,
        )
        return self._insert(row)

    def record_decision(
        self,
        *,
        allowed: bool,
        reason: str,
        symbol: str | None = None,
        action: str = "",
        idempotency_key: str = "",
        candidate: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
        signal_id: int | None = None,
        created_at: datetime | None = None,
    ) -> int:
        """Record every Risk Engine / Decision Maker outcome with its reason."""
        row = DecisionRow(
            created_at=created_at or _utc_now(),
            symbol=symbol.strip().upper() if symbol else None,
            allowed=allowed,
            reason=reason,
            action=action,
            idempotency_key=idempotency_key,
            candidate_json=candidate,
            context_json=context,
            config_snapshot_json=config_snapshot,
            signal_id=signal_id,
        )
        return self._insert(row)

    def record_order(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        entry_price: float,
        stop_price: float,
        idempotency_key: str,
        status: str,
        take_profit: float | None = None,
        risk_pct: float = 0.0,
        ticket: str = "",
        message: str = "",
        decision_id: int | None = None,
        execution: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> int:
        row = OrderRow(
            created_at=created_at or _utc_now(),
            decision_id=decision_id,
            symbol=symbol.strip().upper(),
            side=side.lower(),
            volume=volume,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit=take_profit,
            idempotency_key=idempotency_key,
            risk_pct=risk_pct,
            status=status,
            ticket=ticket,
            message=message,
            execution_json=execution,
        )
        return self._insert(row)

    def record_trade(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        entry_price: float,
        ticket: str = "",
        status: str = "open",
        order_id: int | None = None,
        exit_price: float | None = None,
        stop_price: float | None = None,
        take_profit: float | None = None,
        pnl: float | None = None,
        pnl_r: float | None = None,
        opened_at: datetime | None = None,
        closed_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> int:
        row = TradeRow(
            created_at=created_at or _utc_now(),
            order_id=order_id,
            symbol=symbol.strip().upper(),
            side=side.lower(),
            volume=volume,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_price=stop_price,
            take_profit=take_profit,
            pnl=pnl,
            pnl_r=pnl_r,
            ticket=ticket,
            status=status,
            opened_at=_ensure_aware(opened_at) if opened_at else None,
            closed_at=_ensure_aware(closed_at) if closed_at else None,
        )
        return self._insert(row)

    def record_cost(
        self,
        *,
        kind: str,
        amount: float,
        currency: str = "USD",
        trade_id: int | None = None,
        agent_call_id: int | None = None,
        meta: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> int:
        row = CostRow(
            created_at=created_at or _utc_now(),
            trade_id=trade_id,
            agent_call_id=agent_call_id,
            kind=kind,
            amount=amount,
            currency=currency,
            meta_json=meta,
        )
        return self._insert(row)

    def record_agent_call(
        self,
        *,
        agent_name: str,
        prompt_version: str = "",
        model: str = "",
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int | None = None,
        success: bool = True,
        error_message: str = "",
        decision_id: int | None = None,
        created_at: datetime | None = None,
    ) -> int:
        """Schema ready for M5 agents; safe to call with mocks in tests."""
        row = AgentCallRow(
            created_at=created_at or _utc_now(),
            agent_name=agent_name,
            prompt_version=prompt_version,
            model=model,
            input_json=input_payload,
            output_json=output_payload,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            decision_id=decision_id,
        )
        return self._insert(row)

    def record_system_event(
        self,
        *,
        event_type: str,
        message: str = "",
        payload: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> int:
        row = SystemEventRow(
            created_at=created_at or _utc_now(),
            event_type=event_type,
            message=message,
            payload_json=payload,
        )
        return self._insert(row)

    # --- kill switch ---------------------------------------------------------

    def set_kill_switch_state(
        self,
        state: KillSwitchState,
        *,
        updated_at: datetime | None = None,
    ) -> None:
        when = updated_at or _utc_now()
        with self._session_factory() as session:
            row = session.get(KillSwitchStateRow, KILL_SWITCH_ROW_ID)
            if row is None:
                row = KillSwitchStateRow(
                    id=KILL_SWITCH_ROW_ID,
                    active=state.active,
                    reason=state.reason,
                    engaged_at=state.engaged_at,
                    updated_at=when,
                )
                session.add(row)
            else:
                row.active = state.active
                row.reason = state.reason
                row.engaged_at = state.engaged_at
                row.updated_at = when
            session.commit()

    def get_kill_switch_state(self) -> KillSwitchState:
        with self._session_factory() as session:
            row = session.get(KillSwitchStateRow, KILL_SWITCH_ROW_ID)
            if row is None:
                return KillSwitchState(active=False, reason="", engaged_at=None)
            return KillSwitchState(
                active=row.active,
                reason=row.reason,
                engaged_at=row.engaged_at,
            )

    # --- queries -------------------------------------------------------------

    def query_decisions(
        self,
        *,
        symbol: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[DecisionRow]:
        stmt: Select[tuple[DecisionRow]] = select(DecisionRow).order_by(
            DecisionRow.created_at.asc(), DecisionRow.id.asc()
        )
        stmt = self._apply_time_symbol_filters(
            stmt,
            DecisionRow.created_at,
            DecisionRow.symbol,
            symbol=symbol,
            since=since,
            until=until,
        )
        return self._fetch_all(stmt, limit=limit)

    def query_orders(
        self,
        *,
        symbol: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[OrderRow]:
        stmt: Select[tuple[OrderRow]] = select(OrderRow).order_by(
            OrderRow.created_at.asc(), OrderRow.id.asc()
        )
        stmt = self._apply_time_symbol_filters(
            stmt,
            OrderRow.created_at,
            OrderRow.symbol,
            symbol=symbol,
            since=since,
            until=until,
        )
        return self._fetch_all(stmt, limit=limit)

    def query_trades(
        self,
        *,
        symbol: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[TradeRow]:
        stmt: Select[tuple[TradeRow]] = select(TradeRow).order_by(
            TradeRow.created_at.asc(), TradeRow.id.asc()
        )
        stmt = self._apply_time_symbol_filters(
            stmt,
            TradeRow.created_at,
            TradeRow.symbol,
            symbol=symbol,
            since=since,
            until=until,
        )
        return self._fetch_all(stmt, limit=limit)

    def query_signals(
        self,
        *,
        symbol: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[SignalRow]:
        stmt: Select[tuple[SignalRow]] = select(SignalRow).order_by(
            SignalRow.bar_time.asc(), SignalRow.id.asc()
        )
        stmt = self._apply_time_symbol_filters(
            stmt,
            SignalRow.bar_time,
            SignalRow.symbol,
            symbol=symbol,
            since=since,
            until=until,
        )
        return self._fetch_all(stmt, limit=limit)

    def query_system_events(
        self,
        *,
        event_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[SystemEventRow]:
        stmt: Select[tuple[SystemEventRow]] = select(SystemEventRow).order_by(
            SystemEventRow.created_at.asc(), SystemEventRow.id.asc()
        )
        if event_type is not None:
            stmt = stmt.where(SystemEventRow.event_type == event_type)
        if since is not None:
            stmt = stmt.where(SystemEventRow.created_at >= _ensure_aware(since))
        if until is not None:
            stmt = stmt.where(SystemEventRow.created_at < _ensure_aware(until))
        return self._fetch_all(stmt, limit=limit)

    def query_agent_calls(
        self,
        *,
        agent_name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[AgentCallRow]:
        stmt: Select[tuple[AgentCallRow]] = select(AgentCallRow).order_by(
            AgentCallRow.created_at.asc(), AgentCallRow.id.asc()
        )
        if agent_name is not None:
            stmt = stmt.where(AgentCallRow.agent_name == agent_name)
        if since is not None:
            stmt = stmt.where(AgentCallRow.created_at >= _ensure_aware(since))
        if until is not None:
            stmt = stmt.where(AgentCallRow.created_at < _ensure_aware(until))
        return self._fetch_all(stmt, limit=limit)

    # --- internals -----------------------------------------------------------

    def _insert(self, row: object) -> int:
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)  # type: ignore[attr-defined]

    def _fetch_all(self, stmt: Select[Any], *, limit: int | None) -> list[Any]:
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._session_factory() as session:
            return list(session.scalars(stmt).all())

    @staticmethod
    def _apply_time_symbol_filters(
        stmt: Select[Any],
        time_col: Any,
        symbol_col: Any,
        *,
        symbol: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> Select[Any]:
        if symbol is not None:
            stmt = stmt.where(symbol_col == symbol.strip().upper())
        if since is not None:
            stmt = stmt.where(time_col >= _ensure_aware(since))
        if until is not None:
            stmt = stmt.where(time_col < _ensure_aware(until))
        return stmt


def open_trade_journal(url: str | None = None) -> TradeJournal:
    """
    Open (and create tables for) a journal at ``url`` or the resolved default.

    Default file: ``data/autotrader.db`` under the repo root (SQLite WAL).

    A Postgres ``DATABASE_URL`` is used as-is (psycopg + SSL). This function does
    not fall back to SQLite when that URL is set — connection errors propagate
    so the caller can retry the cycle.
    """
    resolved = resolve_database_url(override=url)
    engine = init_db(create_db_engine(resolved))
    factory = make_session_factory(engine)
    return TradeJournal(factory, database_url=resolved, engine=engine)


def decisions_as_dicts(rows: Sequence[DecisionRow]) -> list[dict[str, Any]]:
    """Small helper for tests / CLI inspection."""
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "symbol": r.symbol,
            "allowed": r.allowed,
            "reason": r.reason,
            "action": r.action,
            "idempotency_key": r.idempotency_key,
        }
        for r in rows
    ]
