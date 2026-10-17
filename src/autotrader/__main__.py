"""CLI entry: `python -m autotrader` prints resolved MODE (default paper)."""

from __future__ import annotations

import sys

from autotrader.config import Mode, load_config, require_non_live_mode
from autotrader.db import resolve_database_url
from autotrader.execution.factory import LiveModeForbiddenError
from autotrader.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    _ = argv  # reserved for future flags
    config = load_config()
    # Hard refuse live at process start (paper/demo phase)
    try:
        require_non_live_mode(config.mode)
    except LiveModeForbiddenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    setup_logging(**config.logging)
    # Smoke output required by M0 acceptance
    print(f"MODE={config.mode.value}")
    if config.mode == Mode.PAPER:
        print("execution=paper (no real MT5 order_send)")
    print(f"database={resolve_database_url()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
