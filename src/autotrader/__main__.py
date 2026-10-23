"""CLI entry: ``python -m autotrader`` / ``autotrader run --once`` / ``paper-ab``."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from autotrader.config import Mode, load_config, require_non_live_mode
from autotrader.db import resolve_database_url
from autotrader.execution.factory import LiveModeForbiddenError
from autotrader.llm.factory import resolve_llm_backend_name, should_force_mock_llm
from autotrader.logging_setup import setup_logging
from autotrader.orchestrator.cycle import build_orchestrator
from autotrader.orchestrator.scheduler import SimpleIntervalScheduler
from autotrader.paper_ab.cli import main as paper_ab_main
from autotrader.telegram.notifier import create_telegram_notifier


def _print_smoke(config) -> None:
    print(f"MODE={config.mode.value}")
    if config.mode == Mode.PAPER:
        print("execution=paper (no real MT5 order_send)")
    print(f"database={resolve_database_url()}")
    # Effective backend (env LLM_BACKEND overrides YAML llm.backend).
    print(f"llm_backend={resolve_llm_backend_name(config_backend=config.llm.backend)}")
    print(f"ab_mode={config.paper_ab.ab_mode.value}")
    tg = create_telegram_notifier()
    print(f"telegram={'enabled' if tg.enabled else 'disabled'}")


def cmd_smoke(_args: argparse.Namespace) -> int:
    config = load_config()
    try:
        require_non_live_mode(config.mode)
    except LiveModeForbiddenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    setup_logging(**config.logging)
    _print_smoke(config)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        require_non_live_mode(config.mode)
    except LiveModeForbiddenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    setup_logging(**config.logging)
    _print_smoke(config)

    # CI / default: mock data + mock LLM. Real LLM when llm.backend=http
    # (or LLM_BACKEND=http) and API key + base URL are present.
    # --mt5-data prefers MT5 candles on Windows with MT5_* creds.
    orch = build_orchestrator(
        config=config,
        force_mock_data=not args.mt5_data,
        force_mock_llm=should_force_mock_llm(config_backend=config.llm.backend),
        force_null_telegram=False,
    )
    orch.heartbeat.mark_up(message="cli_start")

    if args.once or not args.loop:
        now = None
        if args.at:
            now = datetime.fromisoformat(args.at)
            if now.tzinfo is None:
                now = now.replace(tzinfo=UTC)
        result = orch.run_cycle(now=now)
        print(
            f"cycle status={result.status} reason={result.reason} "
            f"symbols={len(result.symbol_results)}"
        )
        for sym in result.symbol_results:
            print(f"  {sym.symbol}: {sym.status} ({sym.reason})")
        orch.heartbeat.mark_down(message="cli_stop")
        return 0 if result.status in {"ok", "skipped"} else 1

    scheduler = SimpleIntervalScheduler(orchestrator=orch)
    results = scheduler.run_forever(max_cycles=args.max_cycles)
    print(f"scheduler cycles={len(results)}")
    return 0


def cmd_paper_ab(args: argparse.Namespace) -> int:
    """Delegate to paper_ab.cli with remaining argv after ``paper-ab``."""
    return int(paper_ab_main(list(args.paper_ab_argv)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autotrader",
        description="AutoTrader paper-first Forex engine (M8 paper A/B harness)",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run orchestrator cycle(s)")
    run_p.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Run a single H1 cycle (default)",
    )
    run_p.add_argument(
        "--loop",
        action="store_true",
        help="Run the interval scheduler (use with --max-cycles in tests)",
    )
    run_p.add_argument(
        "--max-cycles",
        type=int,
        default=1,
        help="Max cycles when --loop is set (default 1)",
    )
    run_p.add_argument(
        "--at",
        type=str,
        default=None,
        help="ISO-8601 UTC clock for the cycle (tests / replay)",
    )
    run_p.add_argument(
        "--mt5-data",
        action="store_true",
        help="Prefer MT5 data backend when available (Windows + creds); default mock",
    )
    run_p.set_defaults(func=cmd_run)

    paper_p = sub.add_parser(
        "paper-ab",
        help="Paper A/B harness (rules-only vs rules+AI); see --help after paper-ab",
        add_help=False,
    )
    paper_p.add_argument(
        "paper_ab_argv",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    paper_p.set_defaults(func=cmd_paper_ab)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Bare `python -m autotrader` → smoke (M0–M5 compat)
    if not argv:
        return cmd_smoke(argparse.Namespace())

    # ``paper-ab`` may receive its own --help / flags; strip a leading ``--`` remnant.
    if argv and argv[0] == "paper-ab":
        rest = argv[1:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        return cmd_paper_ab(argparse.Namespace(paper_ab_argv=rest))

    parser = build_parser()
    # Allow `autotrader run --once` and also `autotrader --help`
    args = parser.parse_args(argv)
    if args.command is None:
        return cmd_smoke(args)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
