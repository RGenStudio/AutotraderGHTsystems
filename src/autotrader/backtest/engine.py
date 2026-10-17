"""
Bar-by-bar backtester — closed bars only, no look-ahead.

Signal at bar ``i`` uses features computed from ``candles[: i+1]`` only.
Entry fills at that bar's close (+ costs). Stop/TP/trail checked on subsequent bars.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from autotrader.backtest.costs import CostModel
from autotrader.backtest.metrics import BacktestReport, compute_report
from autotrader.backtest.types import ClosedTrade, OpenPosition
from autotrader.data.types import Candle
from autotrader.strategy.a_trend import ema_reverse_exit
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.types import Side, Signal, StrategyId


@dataclass(frozen=True, slots=True)
class BacktestResult:
    report: BacktestReport
    trades: list[ClosedTrade]
    signals: list[Signal]


class Backtester:
    """
    Rules-only backtest for one strategy (or all enabled).

    One position at a time. New signals ignored while a position is open.
    """

    def __init__(
        self,
        *,
        engine: StrategyEngine | None = None,
        costs: CostModel | None = None,
        starting_equity: float = 10_000.0,
        strategy_filter: StrategyId | None = None,
    ) -> None:
        if engine is not None:
            self.engine = engine
        elif strategy_filter is not None:
            self.engine = StrategyEngine(enabled=(strategy_filter,))
        else:
            self.engine = StrategyEngine()
        self.costs = costs or CostModel()
        self.starting_equity = starting_equity
        self.strategy_filter = strategy_filter

    def run(self, candles: list[Candle]) -> BacktestResult:
        if len(candles) < 60:
            raise ValueError("need at least 60 closed bars for a meaningful backtest")

        frame = self.engine.features(candles)
        closed: list[ClosedTrade] = []
        all_signals: list[Signal] = []
        position: OpenPosition | None = None

        for i in range(len(frame)):
            if position is not None:
                exited = self._try_exit(frame, i, position)
                if exited is not None:
                    closed.append(exited)
                    position = None

            if position is not None:
                continue

            # Signals only after exits processed; use closed bar i only.
            signals = self.engine.signals_at(frame, i)
            if self.strategy_filter is not None:
                signals = [s for s in signals if s.strategy is self.strategy_filter]
            all_signals.extend(signals)
            if not signals:
                continue

            # Prefer first eligible signal (A before B when both fire).
            sig = signals[0]
            entry_fill = self.costs.apply_entry(sig.entry_price, sig.side)
            risk = abs(entry_fill - sig.stop_price)
            if risk <= 0:
                continue
            position = OpenPosition(
                signal=sig,
                entry_fill=entry_fill,
                stop=sig.stop_price,
                take_profit=sig.take_profit,
                trail_atr_mult=sig.trail_atr_mult,
                entry_bar=i,
                extreme=entry_fill,
                risk_distance=risk,
            )

        if position is not None:
            # Force flat on last bar close.
            last = len(frame) - 1
            closed.append(self._force_close(frame, last, position, reason="end_of_data"))

        report = compute_report(closed, starting_equity=self.starting_equity)
        return BacktestResult(report=report, trades=closed, signals=all_signals)

    def _try_exit(
        self,
        frame: pd.DataFrame,
        index: int,
        position: OpenPosition,
    ) -> ClosedTrade | None:
        if index <= position.entry_bar:
            return None

        row = frame.iloc[index]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        atr_v = float(row["atr14"]) if not pd.isna(row["atr14"]) else position.signal.atr

        # Update trailing extreme first.
        if position.side is Side.LONG:
            position.extreme = max(position.extreme, high)
        else:
            position.extreme = min(position.extreme, low)

        if position.trail_atr_mult is not None and atr_v > 0:
            if position.side is Side.LONG:
                trail = position.extreme - position.trail_atr_mult * atr_v
                position.stop = max(position.stop, trail)
            else:
                trail = position.extreme + position.trail_atr_mult * atr_v
                position.stop = min(position.stop, trail)

        # Stop hit (intrabar): assume stop before TP on same bar (conservative).
        if position.side is Side.LONG and low <= position.stop:
            return self._close_at(frame, index, position, position.stop, "stop")
        if position.side is Side.SHORT and high >= position.stop:
            return self._close_at(frame, index, position, position.stop, "stop")

        # Take profit
        if position.take_profit is not None:
            if position.side is Side.LONG and high >= position.take_profit:
                return self._close_at(frame, index, position, position.take_profit, "take_profit")
            if position.side is Side.SHORT and low <= position.take_profit:
                return self._close_at(frame, index, position, position.take_profit, "take_profit")

        # Strategy A: EMA reverse
        if position.strategy is StrategyId.A and ema_reverse_exit(frame, index, position.side):
            return self._close_at(frame, index, position, close, "ema_reverse")

        # Strategy C: mid-band or max bars
        if position.signal.exit_mid_band:
            mid = row["bb_mid"]
            if not pd.isna(mid):
                mid_v = float(mid)
                if position.side is Side.LONG and close >= mid_v:
                    return self._close_at(frame, index, position, close, "mid_band")
                if position.side is Side.SHORT and close <= mid_v:
                    return self._close_at(frame, index, position, close, "mid_band")

        if position.signal.max_bars is not None:
            held = index - position.entry_bar
            if held >= position.signal.max_bars:
                return self._close_at(frame, index, position, close, "max_bars")

        return None

    def _close_at(
        self,
        frame: pd.DataFrame,
        index: int,
        position: OpenPosition,
        raw_exit: float,
        reason: str,
    ) -> ClosedTrade:
        exit_fill = self.costs.apply_exit(raw_exit, position.side)
        fee = self.costs.fee_per_trade
        if position.side is Side.LONG:
            pnl = (exit_fill - position.entry_fill) - fee
        else:
            pnl = (position.entry_fill - exit_fill) - fee
        pnl_r = pnl / position.risk_distance if position.risk_distance > 0 else 0.0
        return ClosedTrade(
            strategy=position.strategy,
            side=position.side,
            entry_time=position.signal.bar_time,
            exit_time=frame.index[index].to_pydatetime(),
            entry_bar=position.entry_bar,
            exit_bar=index,
            entry_price=position.entry_fill,
            exit_price=exit_fill,
            stop_price=position.stop,
            pnl=pnl,
            pnl_r=pnl_r,
            reason=reason,
            fees=fee,
        )

    def _force_close(
        self,
        frame: pd.DataFrame,
        index: int,
        position: OpenPosition,
        *,
        reason: str,
    ) -> ClosedTrade:
        return self._close_at(frame, index, position, float(frame.iloc[index]["close"]), reason)
