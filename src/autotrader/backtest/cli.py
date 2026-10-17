"""CLI: ``python -m autotrader.backtest`` — run backtest on fixture/CSV (no MT5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autotrader.backtest.costs import CostModel
from autotrader.backtest.engine import Backtester
from autotrader.backtest.io import load_candles_csv, synthetic_candles
from autotrader.data.types import Timeframe
from autotrader.strategy.types import StrategyId


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m autotrader.backtest",
        description="Run Strategy A/B/C backtest on synthetic OHLC or CSV (no MT5).",
    )
    parser.add_argument(
        "--strategy",
        choices=["A", "B", "C", "all"],
        default="all",
        help="Which strategy to backtest (default: all enabled under ADX regime)",
    )
    parser.add_argument(
        "--symbol",
        default="EURUSD",
        help="Symbol label for synthetic/CSV series (default: EURUSD)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional OHLC CSV (columns: time,open,high,low,close[,volume])",
    )
    parser.add_argument(
        "--scenario",
        choices=["mixed", "trend", "range"],
        default="mixed",
        help="Synthetic scenario when --csv is omitted (default: mixed)",
    )
    parser.add_argument("--bars", type=int, default=500, help="Synthetic bar count")
    parser.add_argument("--spread", type=float, default=0.00012, help="Full spread in price")
    parser.add_argument("--slippage", type=float, default=0.00005, help="Slippage per fill")
    parser.add_argument("--fee", type=float, default=0.0, help="Flat fee per closed trade")
    parser.add_argument(
        "--equity",
        type=float,
        default=10_000.0,
        help="Starting equity for drawdown accounting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.csv is not None:
        candles = load_candles_csv(args.csv, symbol=args.symbol, timeframe=Timeframe.H1)
    else:
        candles = synthetic_candles(
            symbol=args.symbol,
            timeframe=Timeframe.H1,
            count=args.bars,
            scenario=args.scenario,
        )

    strategy_filter: StrategyId | None = None
    if args.strategy != "all":
        strategy_filter = StrategyId(args.strategy)

    costs = CostModel(spread=args.spread, slippage=args.slippage, fee_per_trade=args.fee)
    result = Backtester(
        costs=costs,
        starting_equity=args.equity,
        strategy_filter=strategy_filter,
    ).run(candles)

    source = str(args.csv) if args.csv else f"synthetic:{args.scenario}({len(candles)} bars)"
    print(f"source={source}")
    print(f"strategy={args.strategy}")
    print(f"signals={len(result.signals)}")
    for line in result.report.summary_lines():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
