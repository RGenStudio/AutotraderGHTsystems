"""One H1 orchestrator cycle: data → strategy → agents → risk → execution → journal."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from autotrader.active_window import is_within_active_window
from autotrader.agents.pipeline import AgentPipeline, PipelineResult, build_agent_pipeline
from autotrader.config import AppConfig, Mode, load_config, require_non_live_mode
from autotrader.data.factory import create_market_data_provider
from autotrader.data.provider import MarketDataProvider
from autotrader.data.types import Timeframe
from autotrader.execution.factory import create_execution_backend
from autotrader.execution.protocol import ExecutionBackend
from autotrader.execution.types import ApprovedOrder, ExecutionStatus
from autotrader.journal.api import TradeJournal, open_trade_journal
from autotrader.journal.kill_switch import PersistentKillSwitch
from autotrader.journal.persist import (
    persist_execution_outcome,
    persist_risk_outcome,
    persist_signal,
)
from autotrader.kill_switch import KillSwitch
from autotrader.orchestrator.heartbeat import HeartbeatRecorder
from autotrader.risk import (
    CandidateOrder,
    OpenPositionView,
    RiskContext,
    RiskEngine,
    default_risk_limits,
    position_size_risk_pct,
)
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.types import Signal
from autotrader.telegram.notifier import TelegramSender, create_telegram_notifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SymbolCycleResult:
    """Outcome for one symbol inside a cycle."""

    symbol: str
    status: str
    reason: str
    signal_id: int | None = None
    decision_id: int | None = None
    order_id: int | None = None
    trade_id: int | None = None
    pipeline_reason: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Outcome of one full H1 orchestrator pass across configured symbols."""

    status: str
    reason: str
    now: datetime
    mode: Mode
    symbol_results: tuple[SymbolCycleResult, ...] = ()
    heartbeat_id: int | None = None
    errors: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


class Orchestrator:
    """
    Paper-mode H1 cycle runner.

    Pipeline per symbol (when gates allow):
    data → indicators (via StrategyEngine features) → strategy pre-filter →
    (if signal) Agents 1∥2 → 3 → 4 → Risk Engine → execution stub → journal.

    Respects ``active_window``, kill switch, and ``MODE=paper``. Telegram alerts
    on reject / approve / kill / errors never hard-fail the cycle.
    """

    def __init__(
        self,
        *,
        config: AppConfig,
        journal: TradeJournal,
        data: MarketDataProvider,
        strategy: StrategyEngine,
        agents: AgentPipeline,
        risk: RiskEngine,
        execution: ExecutionBackend,
        notifier: TelegramSender,
        heartbeat: HeartbeatRecorder | None = None,
        clock: Callable[[], datetime] | None = None,
        equity: float = 10_000.0,
        bar_count: int = 250,
        parallel_agents: bool = True,
    ) -> None:
        self.config = config
        self.journal = journal
        self.data = data
        self.strategy = strategy
        self.agents = agents
        self.risk = risk
        self.execution = execution
        self.notifier = notifier
        self.heartbeat = heartbeat or HeartbeatRecorder(journal, clock=clock)
        self._clock = clock or (lambda: datetime.now(UTC))
        self.equity = equity
        self.bar_count = bar_count
        self.parallel_agents = parallel_agents
        # Ensure agent pipeline uses parallel 1∥2 when requested
        if hasattr(self.agents, "parallel_12"):
            self.agents.parallel_12 = parallel_agents

    def run_cycle(self, *, now: datetime | None = None) -> CycleResult:
        """Run one H1 cycle across all configured symbols."""
        instant = now or self._clock()
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        else:
            instant = instant.astimezone(UTC)

        errors: list[str] = []
        try:
            require_non_live_mode(self.config.mode)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            errors.append(msg)
            self._soft_notify_error(symbol="-", reason="live_mode_forbidden", detail=msg)
            return CycleResult(
                status="aborted",
                reason="live_mode_forbidden",
                now=instant,
                mode=self.config.mode,
                errors=tuple(errors),
            )

        if self.config.mode != Mode.PAPER and self.config.mode != Mode.BACKTEST:
            # Only paper/backtest allowed; backtest uses its own CLI — treat as paper gate.
            reason = f"unsupported_mode:{self.config.mode.value}"
            self._soft_notify_error(symbol="-", reason=reason)
            return CycleResult(
                status="aborted",
                reason=reason,
                now=instant,
                mode=self.config.mode,
            )

        # Kill switch gate (every cycle)
        if self.risk.check_kill_switch():
            snap = self.risk.kill_switch.snapshot()
            reason = snap.reason or "kill_switch_active"
            self.journal.record_system_event(
                event_type="cycle_skipped",
                message="kill_switch_active",
                payload={"reason": reason},
                created_at=instant,
            )
            self._soft_notify_kill(reason=reason)
            hb = self.heartbeat.beat(message="kill_switch_active", payload={"reason": reason})
            return CycleResult(
                status="skipped",
                reason="kill_switch_active",
                now=instant,
                mode=self.config.mode,
                heartbeat_id=hb,
                meta={"kill_reason": reason},
            )

        # Active window — no new entries outside
        if not is_within_active_window(instant, self.config.active_window):
            self.journal.record_system_event(
                event_type="cycle_skipped",
                message="outside_active_window",
                payload={"now": instant.isoformat()},
                created_at=instant,
            )
            hb = self.heartbeat.beat(message="outside_active_window")
            return CycleResult(
                status="skipped",
                reason="outside_active_window",
                now=instant,
                mode=self.config.mode,
                heartbeat_id=hb,
            )

        symbol_results: list[SymbolCycleResult] = []
        for symbol in self.config.symbols:
            try:
                symbol_results.append(self._run_symbol(symbol, instant))
            except Exception as exc:  # noqa: BLE001 — per-symbol isolation
                logger.exception("symbol cycle failed for %s", symbol)
                err = f"{type(exc).__name__}: {exc}"
                errors.append(f"{symbol}: {err}")
                self._soft_notify_error(symbol=symbol, reason="cycle_exception", detail=err)
                self.journal.record_system_event(
                    event_type="cycle_error",
                    message=err,
                    payload={"symbol": symbol},
                    created_at=instant,
                )
                symbol_results.append(
                    SymbolCycleResult(
                        symbol=symbol,
                        status="error",
                        reason="cycle_exception",
                        errors=(err,),
                    )
                )

        hb = self.heartbeat.beat(
            message="cycle_complete",
            payload={
                "symbols": [r.symbol for r in symbol_results],
                "statuses": [r.status for r in symbol_results],
            },
        )
        overall = _aggregate_status(symbol_results, errors)
        return CycleResult(
            status=overall[0],
            reason=overall[1],
            now=instant,
            mode=self.config.mode,
            symbol_results=tuple(symbol_results),
            heartbeat_id=hb,
            errors=tuple(errors),
        )

    def _run_symbol(self, symbol: str, now: datetime) -> SymbolCycleResult:
        entry_tf = Timeframe(self.config.timeframes.get("entry", "H1"))
        candles = self.data.fetch_candles(symbol, entry_tf, count=self.bar_count)
        if len(candles) < 50:
            return SymbolCycleResult(
                symbol=symbol,
                status="skipped",
                reason="insufficient_bars",
            )

        frame = self.strategy.features(candles)
        last_idx = len(frame) - 1
        signals = self.strategy.signals_at(frame, last_idx)
        if not signals:
            return SymbolCycleResult(
                symbol=symbol,
                status="no_signal",
                reason="no_strategy_signal",
            )

        # Pre-filter: take first candidate (deterministic order A→B→C from engine)
        signal = signals[0]
        signal_id = persist_signal(self.journal, signal, symbol=symbol, created_at=now)
        idem = _idempotency_key(symbol, signal)

        context = _agent_context(symbol, signal, candles[-1].close)
        pipeline = self.agents.run(
            context,
            now=now,
            symbol=symbol,
            idempotency_key=idem,
        )

        if not pipeline.trade_allowed or pipeline.risk_payload is None:
            decision_id = self.journal.record_decision(
                allowed=False,
                reason=pipeline.reason,
                symbol=symbol,
                action="skip",
                idempotency_key=idem,
                candidate=context,
                context={"pipeline": pipeline.reason, "errors": list(pipeline.errors)},
                signal_id=signal_id,
                created_at=now,
            )
            self._soft_notify_reject(
                symbol=symbol, reason=pipeline.reason, detail="; ".join(pipeline.errors)
            )
            return SymbolCycleResult(
                symbol=symbol,
                status="rejected",
                reason=pipeline.reason,
                signal_id=signal_id,
                decision_id=decision_id,
                pipeline_reason=pipeline.reason,
                errors=pipeline.errors,
            )

        return self._risk_and_execute(
            symbol=symbol,
            signal=signal,
            signal_id=signal_id,
            pipeline=pipeline,
            idem=idem,
            now=now,
        )

    def _risk_and_execute(
        self,
        *,
        symbol: str,
        signal: Signal,
        signal_id: int,
        pipeline: PipelineResult,
        idem: str,
        now: datetime,
    ) -> SymbolCycleResult:
        assert pipeline.risk_payload is not None
        open_positions = tuple(
            OpenPositionView(symbol=p.symbol, side=p.side, ticket=p.ticket)
            for p in self.execution.list_open_positions()
        )
        risk_ctx = RiskContext(
            equity=self.equity,
            open_positions=open_positions,
            now=now,
            mode=self.config.mode,
        )
        risk_decision = self.risk.evaluate(
            None,
            risk_ctx,
            raw_json=pipeline.risk_payload,
        )
        candidate: CandidateOrder | None = None
        if isinstance(pipeline.risk_payload, dict):
            try:
                candidate = _candidate_from_payload(pipeline.risk_payload)
            except (KeyError, TypeError, ValueError):
                candidate = None

        decision_id = persist_risk_outcome(
            self.journal,
            risk_decision,
            candidate=candidate,
            context=risk_ctx,
            config_snapshot={
                "mode": self.config.mode.value,
                "risk": self.config.risk.model_dump(),
            },
            signal_id=signal_id,
            created_at=now,
        )

        if not risk_decision.allowed:
            if risk_decision.reason == "max_weekly_drawdown":
                self._soft_notify_kill(reason=risk_decision.reason)
            else:
                self._soft_notify_reject(symbol=symbol, reason=risk_decision.reason)
            return SymbolCycleResult(
                symbol=symbol,
                status="rejected",
                reason=risk_decision.reason,
                signal_id=signal_id,
                decision_id=decision_id,
                pipeline_reason=pipeline.reason,
            )

        assert candidate is not None
        stop_price = float(pipeline.risk_payload.get("stop_loss") or signal.stop_price)
        take_profit = pipeline.risk_payload.get("take_profit")
        if take_profit is not None:
            take_profit = float(take_profit)
        elif signal.take_profit is not None:
            take_profit = float(signal.take_profit)

        volume = position_size_risk_pct(
            self.equity,
            candidate.stop_distance_price,
            candidate.requested_risk_pct,
        )
        # Paper stub uses notionals; clamp to a small demo lot-like size for clarity
        volume = max(volume, 0.01)

        approved = ApprovedOrder(
            symbol=candidate.symbol,
            side=candidate.side,
            volume=volume,
            entry_price=candidate.entry_price,
            stop_price=stop_price,
            take_profit=take_profit,
            idempotency_key=candidate.idempotency_key or idem,
            risk_pct=candidate.requested_risk_pct,
        )
        exec_result = self.execution.send_order(approved)
        order_id, trade_id = persist_execution_outcome(
            self.journal,
            approved,
            exec_result,
            decision_id=decision_id,
            created_at=now,
        )

        if exec_result.status in {ExecutionStatus.FILLED, ExecutionStatus.DUPLICATE}:
            self._soft_notify_approve(
                symbol=symbol,
                reason=risk_decision.reason,
                detail=f"ticket={exec_result.ticket} status={exec_result.status.value}",
            )
            status = "approved" if exec_result.status == ExecutionStatus.FILLED else "duplicate"
        else:
            self._soft_notify_reject(
                symbol=symbol,
                reason=f"execution_{exec_result.status.value}",
                detail=exec_result.message,
            )
            status = "execution_rejected"

        return SymbolCycleResult(
            symbol=symbol,
            status=status,
            reason=risk_decision.reason
            if status == "approved"
            else (exec_result.message or exec_result.status.value),
            signal_id=signal_id,
            decision_id=decision_id,
            order_id=order_id,
            trade_id=trade_id,
            pipeline_reason=pipeline.reason,
        )

    def _soft_notify_approve(self, *, symbol: str, reason: str, detail: str = "") -> None:
        try:
            if hasattr(self.notifier, "notify_approve"):
                self.notifier.notify_approve(symbol=symbol, reason=reason, detail=detail)
            else:
                self.notifier.send(f"[AutoTrader] APPROVE\nsymbol={symbol}\nreason={reason}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram approve notify failed: %s", exc)

    def _soft_notify_reject(self, *, symbol: str, reason: str, detail: str = "") -> None:
        try:
            if hasattr(self.notifier, "notify_reject"):
                self.notifier.notify_reject(symbol=symbol, reason=reason, detail=detail)
            else:
                self.notifier.send(f"[AutoTrader] REJECT\nsymbol={symbol}\nreason={reason}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram reject notify failed: %s", exc)

    def _soft_notify_kill(self, *, reason: str, detail: str = "") -> None:
        try:
            if hasattr(self.notifier, "notify_kill"):
                self.notifier.notify_kill(reason=reason, detail=detail)
            else:
                self.notifier.send(f"[AutoTrader] KILL\nreason={reason}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram kill notify failed: %s", exc)

    def _soft_notify_error(self, *, symbol: str, reason: str, detail: str = "") -> None:
        try:
            if hasattr(self.notifier, "notify_error"):
                self.notifier.notify_error(symbol=symbol, reason=reason, detail=detail)
            else:
                self.notifier.send(f"[AutoTrader] ERROR\nsymbol={symbol}\nreason={reason}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram error notify failed: %s", exc)


def _aggregate_status(
    results: list[SymbolCycleResult],
    errors: list[str],
) -> tuple[str, str]:
    if errors and not results:
        return "error", "cycle_exception"
    if any(r.status == "approved" for r in results):
        return "ok", "approved"
    if any(r.status == "rejected" for r in results):
        return "ok", "rejected"
    if any(r.status == "error" for r in results):
        return "error", "symbol_error"
    if results and all(r.status == "no_signal" for r in results):
        return "ok", "no_signal"
    if not results:
        return "ok", "empty"
    return "ok", results[0].reason


def _idempotency_key(symbol: str, signal: Signal) -> str:
    bar = signal.bar_time.astimezone(UTC).strftime("%Y%m%dT%H%M")
    strategy = signal.strategy.value if hasattr(signal.strategy, "value") else str(signal.strategy)
    side = signal.side.value if hasattr(signal.side, "value") else str(signal.side)
    return f"{symbol}-{strategy}-{side}-{bar}-h1"


def _agent_context(symbol: str, signal: Signal, last_close: float) -> dict[str, Any]:
    strategy = signal.strategy.value if hasattr(signal.strategy, "value") else str(signal.strategy)
    side = signal.side.value if hasattr(signal.side, "value") else str(signal.side)
    return {
        "symbol": symbol,
        "side": side,
        "strategy": strategy,
        "entry_price": signal.entry_price,
        "stop_price": signal.stop_price,
        "take_profit": signal.take_profit,
        "atr": signal.atr,
        "bar_time": signal.bar_time.isoformat(),
        "bar_index": signal.bar_index,
        "reason": signal.reason,
        "last_close": last_close,
    }


def _candidate_from_payload(payload: dict[str, Any]) -> CandidateOrder:
    return CandidateOrder(
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        requested_risk_pct=float(payload["requested_risk_pct"]),
        stop_distance_price=float(payload["stop_distance_price"]),
        entry_price=float(payload["entry_price"]),
        idempotency_key=str(payload.get("idempotency_key") or ""),
        raw_decision=payload,
    )


def build_orchestrator(
    *,
    config: AppConfig | None = None,
    journal: TradeJournal | None = None,
    force_mock_data: bool = True,
    force_mock_llm: bool = True,
    force_null_telegram: bool = False,
    clock: Callable[[], datetime] | None = None,
    equity: float = 10_000.0,
    data: MarketDataProvider | None = None,
    strategy: StrategyEngine | None = None,
    agents: AgentPipeline | None = None,
    risk: RiskEngine | None = None,
    execution: ExecutionBackend | None = None,
    notifier: TelegramSender | None = None,
    kill_switch: KillSwitch | None = None,
) -> Orchestrator:
    """
    Wire production defaults for paper/CI.

    Mock data + mock LLM by default so Linux CI needs no MT5 / API keys.
    """
    cfg = config or load_config()
    require_non_live_mode(cfg.mode)
    j = journal or open_trade_journal()
    ks = kill_switch or PersistentKillSwitch(j)
    data_provider = data or create_market_data_provider(force_mock=force_mock_data)
    strat = strategy or StrategyEngine()
    pipe = agents or build_agent_pipeline(
        journal=j,
        force_mock=force_mock_llm,
        config=cfg,
    )
    risk_engine = risk or RiskEngine(
        limits=cfg.risk if cfg.risk else default_risk_limits(),
        active_window=cfg.active_window,
        kill_switch=ks,
        allowed_symbols=tuple(cfg.symbols),
    )
    exec_backend = execution or create_execution_backend(mode=cfg.mode)
    tg = notifier or create_telegram_notifier(force_null=force_null_telegram)
    hb = HeartbeatRecorder(j, clock=clock)
    return Orchestrator(
        config=cfg,
        journal=j,
        data=data_provider,
        strategy=strat,
        agents=pipe,
        risk=risk_engine,
        execution=exec_backend,
        notifier=tg,
        heartbeat=hb,
        clock=clock,
        equity=equity,
    )

