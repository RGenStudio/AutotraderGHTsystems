"""Paper A/B runner — N synthetic/mock cycles comparing rules-only vs rules+AI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from autotrader.config import (
    AbMode,
    AppConfig,
    Mode,
    PaperAbConfig,
    load_config,
    require_non_live_mode,
)
from autotrader.kill_switch import KillSwitch
from autotrader.paper_ab.metrics import compute_arm_metrics
from autotrader.paper_ab.rules_arm import ai_scripted_decision, rules_only_risk_payload
from autotrader.paper_ab.scenarios import (
    SyntheticCycle,
    generate_synthetic_cycles,
    load_cycles_fixture,
)
from autotrader.paper_ab.types import AbRunResult, ArmName, ClosedPaperTrade
from autotrader.risk import CandidateOrder, OpenPositionView, RiskContext, RiskEngine


@dataclass
class _ArmState:
    name: ArmName
    trades: list[ClosedPaperTrade] = field(default_factory=list)
    equity: float = 10_000.0
    agent4_calls: int = 0
    bad_json_count: int = 0
    cycles_seen: int = 0
    signals_seen: int = 0
    entries_approved: int = 0
    entries_rejected: int = 0
    open_symbols: set[str] = field(default_factory=set)
    risk: RiskEngine | None = None


class PaperAbRunner:
    """
    Execute synthetic/mock paper cycles for one or both A/B arms.

    Does **not** enable live trading. Risk Engine still approves/rejects entries.
    Closed-trade PnL is synthetic (``cycle.pnl_r`` × 1R dollar risk) so CI can
    measure expectancy / max DD without a multi-week MT5 paper session.
    """

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        paper_ab: PaperAbConfig | None = None,
        starting_equity: float | None = None,
        seed: int | None = None,
    ) -> None:
        self.config = config or load_config()
        require_non_live_mode(self.config.mode)
        self.paper_ab = paper_ab or self.config.paper_ab
        self.starting_equity = float(
            starting_equity
            if starting_equity is not None
            else self.paper_ab.starting_equity
        )
        self.seed = int(seed if seed is not None else self.paper_ab.seed)

    def run(
        self,
        *,
        cycles: int | None = None,
        ab_mode: AbMode | str | None = None,
        fixture_path: Path | None = None,
        cycle_list: list[SyntheticCycle] | None = None,
    ) -> AbRunResult:
        mode = AbMode(ab_mode or self.paper_ab.ab_mode)
        n = int(cycles if cycles is not None else self.paper_ab.cycles)
        if n < 1:
            raise ValueError("cycles must be >= 1")

        started = datetime.now(UTC)
        if cycle_list is not None:
            synth = list(cycle_list)[:n]
        elif fixture_path is not None:
            synth = load_cycles_fixture(fixture_path)[:n]
        else:
            synth = generate_synthetic_cycles(
                count=n,
                seed=self.seed,
                symbols=tuple(self.config.symbols),
                signal_rate=self.paper_ab.signal_rate,
                bad_json_rate=self.paper_ab.bad_json_rate,
                ai_skip_rate=self.paper_ab.ai_skip_rate,
                positive_bias=self.paper_ab.positive_bias,
            )

        arms_to_run = _arms_for_mode(mode)
        states = {arm: self._new_state(arm) for arm in arms_to_run}

        for cycle in synth:
            for state in states.values():
                self._run_cycle_arm(cycle, state)

        finished = datetime.now(UTC)
        arms_metrics = {}
        trades_by_arm: dict[str, list[ClosedPaperTrade]] = {}
        for arm, state in states.items():
            first = synth[0].now if synth else None
            last = synth[-1].now if synth else None
            metrics = compute_arm_metrics(
                arm=arm,
                trades=state.trades,
                starting_equity=self.starting_equity,
                agent4_calls=state.agent4_calls,
                bad_json_count=state.bad_json_count,
                cycles_seen=state.cycles_seen,
                signals_seen=state.signals_seen,
                entries_approved=state.entries_approved,
                entries_rejected=state.entries_rejected,
                first_time=first,
                last_time=last,
            )
            arms_metrics[arm.value] = metrics
            trades_by_arm[arm.value] = list(state.trades)

        return AbRunResult(
            ab_mode=mode.value,
            cycles=len(synth),
            seed=self.seed,
            started_at=started,
            finished_at=finished,
            arms=arms_metrics,
            trades_by_arm=trades_by_arm,
            meta={
                "mode": self.config.mode.value,
                "symbols": list(self.config.symbols),
                "starting_equity": self.starting_equity,
                "fixture": str(fixture_path) if fixture_path else None,
            },
        )

    def _new_state(self, arm: ArmName) -> _ArmState:
        ks = KillSwitch()
        risk = RiskEngine(
            limits=self.config.risk,
            active_window=self.config.active_window,
            kill_switch=ks,
            allowed_symbols=tuple(self.config.symbols),
        )
        return _ArmState(
            name=arm,
            equity=self.starting_equity,
            risk=risk,
        )

    def _run_cycle_arm(self, cycle: SyntheticCycle, state: _ArmState) -> None:
        state.cycles_seen += 1
        # Force clock inside active window for risk checks (harness is synthetic).
        now = _ensure_weekday_window(cycle.now)

        if not cycle.has_signal:
            return
        state.signals_seen += 1

        idem = f"paper-ab-{state.name.value}-{cycle.symbol}-{cycle.cycle_index}"
        max_risk = self.config.risk.max_risk_per_trade_pct

        payload: dict[str, Any] | None
        if state.name == ArmName.RULES_ONLY:
            payload = rules_only_risk_payload(
                cycle, idempotency_key=idem, max_risk_pct=max_risk
            )
            reason = "ok"
        else:
            # Agent 4 call counted for every signal (even skip / bad JSON)
            state.agent4_calls += 1
            reason, payload = ai_scripted_decision(
                cycle, idempotency_key=idem, max_risk_pct=max_risk
            )
            if reason == "bad_json":
                state.bad_json_count += 1
                state.entries_rejected += 1
                return
            if reason != "ok" or payload is None:
                state.entries_rejected += 1
                return

        assert payload is not None
        assert state.risk is not None

        # Cap concurrent opens (simulate flatten after each synthetic close)
        open_views = tuple(
            OpenPositionView(symbol=s, side="long") for s in state.open_symbols
        )
        ctx = RiskContext(
            equity=state.equity,
            open_positions=open_views,
            now=now,
            mode=Mode.PAPER,
        )
        decision = state.risk.evaluate(None, ctx, raw_json=payload)
        if not decision.allowed:
            state.entries_rejected += 1
            return

        candidate = CandidateOrder(
            symbol=str(payload["symbol"]),
            side=str(payload["side"]),
            requested_risk_pct=float(payload["requested_risk_pct"]),
            stop_distance_price=float(payload["stop_distance_price"]),
            entry_price=float(payload["entry_price"]),
            idempotency_key=str(payload["idempotency_key"]),
            raw_decision=payload,
        )

        # 1R dollar risk from configured % of equity
        risk_dollars = state.equity * (candidate.requested_risk_pct / 100.0)
        pnl = cycle.pnl_r * risk_dollars
        # Synthetic exit: immediate close for metrics (paper harness, not live hold)
        exit_time = now + timedelta(hours=1)
        # Approximate exit price from R
        if candidate.side == "long":
            exit_price = candidate.entry_price + cycle.pnl_r * candidate.stop_distance_price
        else:
            exit_price = candidate.entry_price - cycle.pnl_r * candidate.stop_distance_price

        trade = ClosedPaperTrade(
            cycle_index=cycle.cycle_index,
            symbol=candidate.symbol,
            side=candidate.side,
            entry_time=now,
            exit_time=exit_time,
            entry_price=candidate.entry_price,
            exit_price=exit_price,
            stop_price=float(payload.get("stop_loss") or cycle.stop_price),
            pnl_r=cycle.pnl_r,
            pnl=pnl,
            reason="synthetic_close",
            arm=state.name,
            meta={"pipeline_reason": reason, "strategy": cycle.strategy},
        )
        state.trades.append(trade)
        state.equity += pnl
        state.entries_approved += 1
        # Flat after synthetic close — no multi-bar holds in the harness
        state.open_symbols.clear()


def run_paper_ab(
    *,
    cycles: int = 50,
    ab_mode: AbMode | str = AbMode.BOTH,
    seed: int = 42,
    config: AppConfig | None = None,
    fixture_path: Path | None = None,
) -> AbRunResult:
    """Convenience entry used by CLI and tests."""
    cfg = config or load_config()
    runner = PaperAbRunner(config=cfg, seed=seed)
    return runner.run(cycles=cycles, ab_mode=ab_mode, fixture_path=fixture_path)


def _arms_for_mode(mode: AbMode) -> list[ArmName]:
    if mode == AbMode.RULES_ONLY:
        return [ArmName.RULES_ONLY]
    if mode == AbMode.RULES_PLUS_AI:
        return [ArmName.RULES_PLUS_AI]
    return [ArmName.RULES_ONLY, ArmName.RULES_PLUS_AI]


def _ensure_weekday_window(now: datetime) -> datetime:
    """
    Normalize synthetic clocks for Risk Engine.

    Project default active_window is effectively 24h; still snap weekends to a
    weekday mid-day so harnesses stay deterministic if an operator narrows the
    window again.
    """
    instant = now if now.tzinfo else now.replace(tzinfo=UTC)
    instant = instant.astimezone(UTC)
    if instant.weekday() >= 5:
        # Move to next Monday 15:00 UTC
        days = 7 - instant.weekday()
        instant = instant + timedelta(days=days)
        instant = instant.replace(hour=15, minute=0, second=0, microsecond=0)
    return instant
