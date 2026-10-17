"""M4 Trade Journal — SQLite round-trips, queries, M3 persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from autotrader.config import Mode
from autotrader.db import create_db_engine, init_db, resolve_database_url
from autotrader.execution.types import ApprovedOrder, ExecutionResult, ExecutionStatus
from autotrader.journal import (
    PersistentKillSwitch,
    open_trade_journal,
    persist_execution_outcome,
    persist_risk_outcome,
    persist_signal,
)
from autotrader.risk import (
    CandidateOrder,
    RiskContext,
    RiskDecision,
    RiskEngine,
    default_risk_limits,
)
from autotrader.strategy.types import Side, Signal, StrategyId


@pytest.fixture
def journal(tmp_path: Path):
    """Temp on-disk SQLite DB (WAL) — not the shared default file."""
    url = f"sqlite:///{tmp_path / 'journal-test.db'}"
    return open_trade_journal(url)


def test_resolve_database_url_default_under_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = resolve_database_url()
    assert url.startswith("sqlite:///")
    assert url.endswith("data/autotrader.db") or url.endswith("data\\autotrader.db")


def test_resolve_database_url_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "custom.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    assert resolve_database_url() == f"sqlite:///{path}"


def test_sqlite_wal_mode(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'wal.db'}"
    engine = init_db(create_db_engine(url))
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert str(mode).lower() == "wal"


def test_record_and_query_decision_by_symbol_and_time(journal) -> None:
    t0 = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)

    journal.record_decision(
        allowed=True,
        reason="ok",
        symbol="EURUSD",
        action="enter",
        idempotency_key="k1",
        candidate={"side": "long"},
        created_at=t0,
    )
    journal.record_decision(
        allowed=False,
        reason="max_open_positions",
        symbol="USDJPY",
        action="reject",
        idempotency_key="k2",
        created_at=t1,
    )
    journal.record_decision(
        allowed=False,
        reason="outside_active_window",
        symbol="EURUSD",
        action="reject",
        idempotency_key="k3",
        created_at=t2,
    )

    eurusd = journal.query_decisions(symbol="EURUSD")
    assert len(eurusd) == 2
    assert all(r.symbol == "EURUSD" for r in eurusd)
    assert eurusd[0].reason == "ok"
    assert eurusd[0].candidate_json == {"side": "long"}

    window = journal.query_decisions(since=t1, until=t2 + timedelta(seconds=1))
    assert len(window) == 2
    assert {r.symbol for r in window} == {"EURUSD", "USDJPY"}

    only_jpy = journal.query_decisions(symbol="usdjpy", since=t0, until=t2)
    assert len(only_jpy) == 1
    assert only_jpy[0].reason == "max_open_positions"


def test_decision_round_trip_includes_reason_and_config(journal) -> None:
    cfg = {"risk": {"max_risk_per_trade_pct": 0.5}, "mode": "paper"}
    decision_id = journal.record_decision(
        allowed=False,
        reason="bad_json",
        action="reject",
        config_snapshot=cfg,
        candidate=None,
        context={"equity": 10_000},
    )
    rows = journal.query_decisions()
    assert len(rows) == 1
    assert rows[0].id == decision_id
    assert rows[0].reason == "bad_json"
    assert rows[0].allowed is False
    assert rows[0].config_snapshot_json == cfg
    assert rows[0].context_json == {"equity": 10_000}


def test_persist_risk_and_execution_from_m3_types(journal) -> None:
    engine = RiskEngine(limits=default_risk_limits())
    candidate = CandidateOrder(
        symbol="EURUSD",
        side="long",
        requested_risk_pct=0.5,
        stop_distance_price=0.0010,
        entry_price=1.10,
        idempotency_key="signal-h1-1",
    )
    ctx = RiskContext(
        equity=10_000,
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
        mode=Mode.PAPER,
    )
    decision = engine.evaluate(candidate, ctx)
    assert decision.allowed is True

    decision_id = persist_risk_outcome(
        journal,
        decision,
        candidate=candidate,
        context=ctx,
        config_snapshot={"mode": "paper"},
    )
    order = ApprovedOrder(
        symbol=candidate.symbol,
        side=candidate.side,
        volume=0.1,
        entry_price=candidate.entry_price,
        stop_price=1.0990,
        take_profit=None,
        idempotency_key=candidate.idempotency_key,
        risk_pct=candidate.requested_risk_pct,
    )
    result = ExecutionResult(
        status=ExecutionStatus.FILLED,
        ticket="paper-1",
        message="paper_fill",
        idempotency_key=order.idempotency_key,
    )
    order_id, trade_id = persist_execution_outcome(
        journal, order, result, decision_id=decision_id
    )
    assert order_id > 0
    assert trade_id is not None

    decisions = journal.query_decisions(symbol="EURUSD")
    assert len(decisions) == 1
    assert decisions[0].reason == "ok"
    assert decisions[0].allowed is True
    assert decisions[0].idempotency_key == "signal-h1-1"

    orders = journal.query_orders(symbol="EURUSD")
    assert len(orders) == 1
    assert orders[0].status == "filled"
    assert orders[0].ticket == "paper-1"
    assert orders[0].decision_id == decision_id

    trades = journal.query_trades(symbol="EURUSD")
    assert len(trades) == 1
    assert trades[0].status == "open"
    assert trades[0].order_id == order_id


def test_persist_rejected_risk_no_order(journal) -> None:
    decision = RiskDecision(False, "kill_switch_active")
    candidate = CandidateOrder(
        symbol="USDJPY",
        side="short",
        requested_risk_pct=0.5,
        stop_distance_price=0.10,
        entry_price=150.0,
        idempotency_key="blocked",
    )
    did = persist_risk_outcome(journal, decision, candidate=candidate)
    rows = journal.query_decisions(symbol="USDJPY")
    assert len(rows) == 1
    assert rows[0].id == did
    assert rows[0].allowed is False
    assert rows[0].reason == "kill_switch_active"
    assert journal.query_orders() == []


def test_persist_signal_round_trip(journal) -> None:
    bar_time = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
    signal = Signal(
        strategy=StrategyId.A,
        side=Side.LONG,
        bar_index=42,
        bar_time=bar_time,
        entry_price=1.0850,
        stop_price=1.0800,
        atr=0.0012,
        reason="ema_cross",
    )
    sid = persist_signal(journal, signal, symbol="EURUSD")
    rows = journal.query_signals(
        symbol="EURUSD",
        since=bar_time,
        until=bar_time + timedelta(hours=1),
    )
    assert len(rows) == 1
    assert rows[0].id == sid
    assert rows[0].strategy == "A"
    assert rows[0].reason == "ema_cross"
    assert rows[0].payload_json is not None
    assert rows[0].payload_json["bar_index"] == 42


def test_costs_agent_calls_system_events(journal) -> None:
    aid = journal.record_agent_call(
        agent_name="decision_maker",
        prompt_version="v0-stub",
        model="mock",
        input_payload={"symbol": "EURUSD"},
        output_payload={"action": "skip"},
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.0001,
        success=True,
    )
    journal.record_cost(kind="llm_api", amount=0.0001, agent_call_id=aid)
    journal.record_system_event(
        event_type="engine_up",
        message="paper start",
        payload={"mode": "paper"},
    )
    calls = journal.query_agent_calls(agent_name="decision_maker")
    assert len(calls) == 1
    assert calls[0].prompt_version == "v0-stub"
    events = journal.query_system_events(event_type="engine_up")
    assert len(events) == 1
    assert events[0].payload_json == {"mode": "paper"}


def test_persistent_kill_switch_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'ks.db'}"
    journal = open_trade_journal(url)
    ks = PersistentKillSwitch(journal)
    assert ks.is_active() is False

    when = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    ks.engage("max_weekly_drawdown", when=when)
    assert ks.is_active() is True
    assert journal.get_kill_switch_state().active is True
    assert journal.get_kill_switch_state().reason == "max_weekly_drawdown"

    # Re-open journal / kill switch — state survives
    journal2 = open_trade_journal(url)
    ks2 = PersistentKillSwitch(journal2)
    assert ks2.is_active() is True
    assert ks2.snapshot().reason == "max_weekly_drawdown"

    ks2.clear()
    assert ks2.is_active() is False
    assert open_trade_journal(url).get_kill_switch_state().active is False

    events = journal2.query_system_events()
    types = [e.event_type for e in events]
    assert "kill_switch_engage" in types
    assert "kill_switch_clear" in types


def test_tables_exist(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'schema.db'}"
    engine = init_db(create_db_engine(url))
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    expected = {
        "signals",
        "agent_calls",
        "decisions",
        "orders",
        "trades",
        "costs",
        "system_events",
        "kill_switch_state",
    }
    assert expected.issubset(names)
