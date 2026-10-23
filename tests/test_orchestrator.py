"""M6 orchestrator — H1 cycle, gates, journal, soft Telegram."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from autotrader.agents.calendar import StubNewsCalendar
from autotrader.agents.pipeline import AgentPipeline
from autotrader.config import AppConfig, Mode, load_config
from autotrader.data.mock import MockMarketDataProvider
from autotrader.execution.paper import PaperExecutionBackend
from autotrader.journal import open_trade_journal
from autotrader.kill_switch import KillSwitch
from autotrader.llm import LLMClient, MockLLMBackend
from autotrader.orchestrator import (
    Orchestrator,
    SimpleIntervalScheduler,
    build_orchestrator,
)
from autotrader.orchestrator.heartbeat import (
    EVENT_ENGINE_DOWN,
    EVENT_ENGINE_UP,
    EVENT_HEARTBEAT,
    HeartbeatRecorder,
)
from autotrader.risk import RiskEngine, default_risk_limits
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.types import Side, Signal, StrategyId
from autotrader.telegram import NullTelegramNotifier


def _tech() -> dict:
    return {
        "direction": "long",
        "confidence": 75,
        "structure_supports_signal": True,
        "key_levels": [1.08, 1.09],
        "reasoning": "H4 uptrend supports long",
    }


def _news(*, no_trade: bool = False) -> dict:
    return {
        "bias": "neutral",
        "impact_level": "low" if not no_trade else "high",
        "no_trade_news": no_trade,
        "reasoning": "quiet" if not no_trade else "NFP",
        "blackout_events": [] if not no_trade else ["NFP"],
    }


def _risk() -> dict:
    return {
        "should_trade": True,
        "risk_pct": 0.5,
        "stop_loss": 1.0810,
        "take_profit": 1.0930,
        "reasoning": "0.5% within ceiling",
    }


def _decision() -> dict:
    return {
        "action": "enter_long",
        "symbol": "EURUSD",
        "risk_pct": 0.5,
        "stop_loss": 1.0810,
        "take_profit": 1.0930,
        "entry_price": 1.0850,
        "confidence": 68,
        "reasoning": "aligned",
        "conflicts_noted": [],
        "idempotency_key": "",
    }


class _FixedStrategy(StrategyEngine):
    """Always emit one EURUSD long signal on the last bar."""

    def signals_at(self, frame, index: int) -> list[Signal]:  # type: ignore[override]
        bar_time = frame.index[index].to_pydatetime()
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=UTC)
        close = float(frame.iloc[index]["close"])
        raw_atr = frame.iloc[index]["atr14"] if "atr14" in frame.columns else 0.001
        atr = float(raw_atr)
        if math.isnan(atr) or atr <= 0:
            atr = 0.001
        return [
            Signal(
                strategy=StrategyId.A,
                side=Side.LONG,
                bar_index=index,
                bar_time=bar_time,
                entry_price=close,
                stop_price=close - 2 * atr,
                atr=atr,
                take_profit=close + 3 * atr,
                reason="test_fixed_signal",
            )
        ]


class _RecordingNotifier(NullTelegramNotifier):
    def __init__(self) -> None:
        self.messages: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        _ = parse_mode
        self.messages.append(text)
        return True

    def notify_approve(self, *, symbol: str, reason: str, detail: str = "") -> bool:
        return self.send(f"APPROVE {symbol} {reason} {detail}")

    def notify_reject(self, *, symbol: str, reason: str, detail: str = "") -> bool:
        return self.send(f"REJECT {symbol} {reason} {detail}")

    def notify_kill(self, *, reason: str, detail: str = "") -> bool:
        return self.send(f"KILL {reason} {detail}")

    def notify_error(self, *, symbol: str, reason: str, detail: str = "") -> bool:
        return self.send(f"ERROR {symbol} {reason} {detail}")


class _BoomNotifier(_RecordingNotifier):
    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        raise RuntimeError("telegram down")


@pytest.fixture
def journal(tmp_path: Path):
    return open_trade_journal(f"sqlite:///{tmp_path / 'm6.db'}")


def _agent_pipeline(journal) -> AgentPipeline:
    backend = MockLLMBackend()
    backend.set_agent_response("technical", _tech())
    backend.set_agent_response("news", _news())
    backend.set_agent_response("risk_manager", _risk())
    backend.set_agent_response("decision_maker", _decision())
    client = LLMClient(backend, timeout_s=5)
    return AgentPipeline(
        client,
        journal=journal,
        calendar=StubNewsCalendar(events=[]),
        parallel_12=True,
    )


def _make_orch(
    journal,
    *,
    kill_switch: KillSwitch | None = None,
    notifier=None,
    strategy: StrategyEngine | None = None,
    symbols: list[str] | None = None,
    clock=None,
) -> Orchestrator:
    cfg = load_config()
    if symbols is not None:
        cfg = cfg.model_copy(update={"symbols": symbols})
    ks = kill_switch or KillSwitch()
    return Orchestrator(
        config=cfg,
        journal=journal,
        data=MockMarketDataProvider(symbols=tuple(cfg.symbols)),
        strategy=strategy or _FixedStrategy(),
        agents=_agent_pipeline(journal),
        risk=RiskEngine(
            limits=default_risk_limits(),
            active_window=cfg.active_window,
            kill_switch=ks,
            allowed_symbols=tuple(cfg.symbols),
        ),
        execution=PaperExecutionBackend(),
        notifier=notifier or _RecordingNotifier(),
        clock=clock,
        equity=10_000.0,
    )


def test_cycle_approve_inside_window(journal) -> None:
    notifier = _RecordingNotifier()
    orch = _make_orch(journal, notifier=notifier, symbols=["EURUSD"])
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)  # Wed inside window
    result = orch.run_cycle(now=now)
    assert result.status == "ok"
    assert result.reason == "approved"
    assert len(result.symbol_results) == 1
    assert result.symbol_results[0].status == "approved"
    assert any("APPROVE" in m for m in notifier.messages)
    # Journal: signal + decision + order + heartbeat
    assert journal.query_signals(symbol="EURUSD")
    decisions = journal.query_decisions(symbol="EURUSD")
    assert decisions and decisions[-1].allowed is True
    assert journal.query_orders(symbol="EURUSD")
    beats = journal.query_system_events(event_type=EVENT_HEARTBEAT)
    assert beats


def test_cycle_skips_outside_active_window(journal) -> None:
    from autotrader.config import ActiveWindow

    # Default window is 24h — use a narrow window to exercise the skip path.
    orch = _make_orch(journal, symbols=["EURUSD"])
    orch.config = orch.config.model_copy(
        update={
            "active_window": ActiveWindow(
                timezone="UTC", weekdays_only=True, start="12:00", end="21:00"
            )
        }
    )
    orch.risk.active_window = orch.config.active_window
    now = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)  # before 12:00
    result = orch.run_cycle(now=now)
    assert result.status == "skipped"
    assert result.reason == "outside_active_window"
    assert journal.query_signals() == []


def test_cycle_skips_kill_switch_and_notifies(journal) -> None:
    ks = KillSwitch()
    ks.engage("operator_pause")
    notifier = _RecordingNotifier()
    orch = _make_orch(journal, kill_switch=ks, notifier=notifier, symbols=["EURUSD"])
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    result = orch.run_cycle(now=now)
    assert result.status == "skipped"
    assert result.reason == "kill_switch_active"
    assert any("KILL" in m for m in notifier.messages)


def test_telegram_down_does_not_fail_cycle(journal) -> None:
    orch = _make_orch(journal, notifier=_BoomNotifier(), symbols=["EURUSD"])
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    result = orch.run_cycle(now=now)
    assert result.status == "ok"
    assert result.symbol_results[0].status == "approved"


def test_no_signal_path_with_real_strategy(journal) -> None:
    # Default mock OHLC + real StrategyEngine often yields no signal at last bar.
    cfg = load_config().model_copy(update={"symbols": ["EURUSD"]})
    orch = Orchestrator(
        config=cfg,
        journal=journal,
        data=MockMarketDataProvider(symbols=("EURUSD",)),
        strategy=StrategyEngine(),
        agents=_agent_pipeline(journal),
        risk=RiskEngine(limits=default_risk_limits(), active_window=cfg.active_window),
        execution=PaperExecutionBackend(),
        notifier=NullTelegramNotifier(),
    )
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    result = orch.run_cycle(now=now)
    assert result.status == "ok"
    assert result.reason in {"no_signal", "rejected", "approved"}


def test_heartbeat_up_down(journal) -> None:
    clock_times = iter(
        [
            datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
            datetime(2026, 10, 14, 12, 5, tzinfo=UTC),
            datetime(2026, 10, 14, 12, 10, tzinfo=UTC),
        ]
    )
    hb = HeartbeatRecorder(journal, clock=lambda: next(clock_times))
    assert hb.mark_up() > 0
    assert hb.is_up
    assert hb.beat() > 0
    assert hb.mark_down() > 0
    assert not hb.is_up
    ups = journal.query_system_events(event_type=EVENT_ENGINE_UP)
    downs = journal.query_system_events(event_type=EVENT_ENGINE_DOWN)
    beats = journal.query_system_events(event_type=EVENT_HEARTBEAT)
    assert len(ups) == 1 and len(downs) == 1 and len(beats) == 1


def test_scheduler_fake_clock(journal) -> None:
    start = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    orch = _make_orch(journal, symbols=["EURUSD"])
    scheduler = SimpleIntervalScheduler(
        orchestrator=orch,
        interval=timedelta(hours=1),
        sleep=lambda _s: None,
    )
    results = scheduler.run_until(
        start=start,
        stop_at=start + timedelta(hours=3),
        interval=timedelta(hours=1),
    )
    assert len(results) == 3
    ups = journal.query_system_events(event_type=EVENT_ENGINE_UP)
    downs = journal.query_system_events(event_type=EVENT_ENGINE_DOWN)
    assert ups and downs


def test_scheduler_run_forever_max_cycles(journal) -> None:
    """run_forever with max_cycles>1 must schedule more than one cycle (mock sleep)."""
    orch = _make_orch(journal, symbols=["EURUSD"])
    sleeps: list[float] = []
    scheduler = SimpleIntervalScheduler(
        orchestrator=orch,
        interval=timedelta(hours=1),
        sleep=lambda s: sleeps.append(s),
    )
    results = scheduler.run_forever(max_cycles=3)
    assert len(results) == 3
    assert len(sleeps) == 2
    downs = journal.query_system_events(event_type=EVENT_ENGINE_DOWN)
    assert downs and downs[-1].message == "scheduler_stop"


def test_build_orchestrator_paper_mock(tmp_path: Path) -> None:
    journal = open_trade_journal(f"sqlite:///{tmp_path / 'build.db'}")
    orch = build_orchestrator(
        journal=journal,
        force_mock_data=True,
        force_mock_llm=True,
        force_null_telegram=True,
    )
    assert orch.config.mode == Mode.PAPER
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    result = orch.run_cycle(now=now)
    assert result.status in {"ok", "skipped"}
    assert result.mode == Mode.PAPER


def test_parallel_agents_with_agent_keyed_mock(journal) -> None:
    """Agents 1∥2 resolve correctly via responses_by_agent (not FIFO queue)."""
    pipe = _agent_pipeline(journal)
    assert pipe.parallel_12 is True
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    result = pipe.run(
        {
            "symbol": "EURUSD",
            "side": "long",
            "entry_price": 1.085,
            "strategy": "A",
        },
        now=now,
        symbol="EURUSD",
        idempotency_key="par-1",
    )
    assert result.trade_allowed is True
    assert result.meta.get("parallel_12") is True


def test_mode_paper_enforced(journal, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODE", "live")
    cfg = AppConfig(mode=Mode.LIVE, symbols=["EURUSD"])
    orch = Orchestrator(
        config=cfg,
        journal=journal,
        data=MockMarketDataProvider(symbols=("EURUSD",)),
        strategy=_FixedStrategy(),
        agents=_agent_pipeline(journal),
        risk=RiskEngine(limits=default_risk_limits()),
        execution=PaperExecutionBackend(),
        notifier=NullTelegramNotifier(),
    )
    result = orch.run_cycle(now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC))
    assert result.status == "aborted"
    assert result.reason == "live_mode_forbidden"
