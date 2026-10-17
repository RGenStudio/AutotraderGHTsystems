"""Backtester: no look-ahead, metrics, CSV/synthetic path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotrader.backtest.costs import CostModel
from autotrader.backtest.engine import Backtester
from autotrader.backtest.io import load_candles_csv, synthetic_candles
from autotrader.backtest.metrics import compute_report
from autotrader.backtest.types import ClosedTrade
from autotrader.data.mock import generate_fixture_candles
from autotrader.data.types import Timeframe
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.types import Side, StrategyId

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_ohlc.csv"


def test_no_lookahead_prefix_signals_stable() -> None:
    """Signals on bar i must be identical when computed on data[:i+1] vs full series."""
    candles = generate_fixture_candles("EURUSD", Timeframe.H1, count=280)
    engine = StrategyEngine()
    full = engine.features(candles)

    for i in range(60, len(candles), 17):
        prefix = candles[: i + 1]
        prefix_frame = engine.features(prefix)
        full_sigs = engine.signals_at(full, i)
        prefix_sigs = engine.signals_at(prefix_frame, i)
        assert len(full_sigs) == len(prefix_sigs)
        for a, b in zip(full_sigs, prefix_sigs, strict=True):
            assert a.strategy == b.strategy
            assert a.side == b.side
            assert a.entry_price == b.entry_price
            assert a.stop_price == b.stop_price
            assert a.bar_index == b.bar_index


def test_backtest_runs_on_synthetic_without_mt5() -> None:
    candles = synthetic_candles(count=400, scenario="mixed")
    result = Backtester(costs=CostModel(spread=0.0001, slippage=0.0)).run(candles)
    assert result.report.trades >= 0
    assert 0.0 <= result.report.win_rate <= 1.0
    assert result.report.equity_end == pytest.approx(
        10_000.0 + result.report.net_pnl
    )


def test_backtest_strategy_filter_a() -> None:
    candles = synthetic_candles(count=500, scenario="trend")
    result = Backtester(strategy_filter=StrategyId.A).run(candles)
    assert all(t.strategy is StrategyId.A for t in result.trades)
    assert all(s.strategy is StrategyId.A for s in result.signals)


def test_synthetic_trend_produces_a_or_b_signals() -> None:
    candles = synthetic_candles(count=600, scenario="trend")
    result = Backtester().run(candles)
    strategies = {s.strategy for s in result.signals}
    assert strategies & {StrategyId.A, StrategyId.B}
    assert StrategyId.C not in strategies or all(
        s.strategy is not StrategyId.C for s in result.signals
    )


def test_synthetic_range_produces_c_signals() -> None:
    candles = synthetic_candles(count=600, scenario="range")
    result = Backtester(strategy_filter=StrategyId.C).run(candles)
    assert len(result.signals) >= 1
    assert all(s.strategy is StrategyId.C for s in result.signals)


def test_metrics_expectancy_and_drawdown() -> None:
    trades = [
        ClosedTrade(
            strategy=StrategyId.A,
            side=Side.LONG,
            entry_time=datetime(2024, 1, 1, tzinfo=UTC),
            exit_time=datetime(2024, 1, 2, tzinfo=UTC),
            entry_bar=0,
            exit_bar=1,
            entry_price=1.0,
            exit_price=1.1,
            stop_price=0.9,
            pnl=0.1,
            pnl_r=1.0,
            reason="tp",
        ),
        ClosedTrade(
            strategy=StrategyId.A,
            side=Side.LONG,
            entry_time=datetime(2024, 1, 3, tzinfo=UTC),
            exit_time=datetime(2024, 1, 4, tzinfo=UTC),
            entry_bar=2,
            exit_bar=3,
            entry_price=1.0,
            exit_price=0.9,
            stop_price=0.9,
            pnl=-0.1,
            pnl_r=-1.0,
            reason="stop",
        ),
    ]
    report = compute_report(trades, starting_equity=1.0)
    assert report.trades == 2
    assert report.win_rate == 0.5
    assert report.expectancy_r == pytest.approx(0.0)
    assert report.reward_risk == pytest.approx(1.0)
    assert report.max_drawdown == pytest.approx(0.1)


def test_load_csv_fixture() -> None:
    candles = load_candles_csv(FIXTURE_CSV, symbol="EURUSD")
    assert len(candles) == 5
    assert candles[0].time.tzinfo is not None
    assert candles[0].open == pytest.approx(1.1)


def test_cost_model_adverse() -> None:
    costs = CostModel(spread=0.0002, slippage=0.0001)
    long_entry = costs.apply_entry(1.0, Side.LONG)
    long_exit = costs.apply_exit(1.0, Side.LONG)
    assert long_entry > 1.0
    assert long_exit < 1.0
