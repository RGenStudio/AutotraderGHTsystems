"""CLI: ``python -m autotrader paper-ab`` / ``python -m autotrader.paper_ab``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autotrader.config import AbMode, Mode, load_config, require_non_live_mode
from autotrader.execution.factory import LiveModeForbiddenError
from autotrader.logging_setup import setup_logging
from autotrader.paper_ab.gates import check_section13_gates
from autotrader.paper_ab.report import DEFAULT_REPORTS_DIR, write_ab_report
from autotrader.paper_ab.runner import run_paper_ab


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m autotrader paper-ab",
        description=(
            "Paper A/B harness: rules-only vs rules+AI on synthetic/mock cycles. "
            "Writes reports under reports/ and evaluates §13 gates (never enables live)."
        ),
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Number of synthetic cycles (default: config paper_ab.cycles or 50)",
    )
    parser.add_argument(
        "--ab-mode",
        choices=[m.value for m in AbMode],
        default=None,
        help="rules_only | rules_plus_ai | both (default: config / both)",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for synthetic cycles")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Optional JSON cycle fixture (tests / reproducible demos)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Report directory (default: {DEFAULT_REPORTS_DIR})",
    )
    parser.add_argument(
        "--basename",
        type=str,
        default=None,
        help="Report filename stem (default: paper-ab-<UTC stamp>)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print metrics only; do not write report files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    try:
        require_non_live_mode(config.mode)
    except LiveModeForbiddenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if config.mode == Mode.LIVE:
        print("ERROR: paper-ab refuses MODE=live", file=sys.stderr)
        return 2

    setup_logging(**config.logging)

    cycles = args.cycles if args.cycles is not None else config.paper_ab.cycles
    ab_mode = args.ab_mode or config.paper_ab.ab_mode.value
    seed = args.seed if args.seed is not None else config.paper_ab.seed

    print(f"MODE={config.mode.value}")
    print(f"ab_mode={ab_mode}")
    print(f"cycles={cycles}")
    print(f"seed={seed}")
    print("live_enabled=false")

    result = run_paper_ab(
        cycles=cycles,
        ab_mode=ab_mode,
        seed=seed,
        config=config,
        fixture_path=args.fixture,
    )
    gate = check_section13_gates(result, thresholds=config.paper_ab.gates)

    for name, metrics in result.arms.items():
        print(f"--- {name} ---")
        for line in metrics.summary_lines():
            print(line)

    print("--- §13 gates ---")
    for line in gate.summary_lines():
        print(line)

    if not args.no_write:
        paths = write_ab_report(
            result,
            gate,
            output_dir=args.output_dir,
            basename=args.basename,
        )
        print(f"report_json={paths['json']}")
        print(f"report_md={paths['markdown']}")

    # Exit 0 even on gate fail — harness ran successfully; gate is informational.
    # Non-zero only for hard errors (live mode, bad args).
    return 0


if __name__ == "__main__":
    sys.exit(main())
