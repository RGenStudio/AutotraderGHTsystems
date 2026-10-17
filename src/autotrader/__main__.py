"""CLI entry: `python -m autotrader` prints resolved MODE (default paper)."""

from __future__ import annotations

import sys

from autotrader.config import load_config
from autotrader.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    _ = argv  # reserved for future flags
    config = load_config()
    setup_logging(**config.logging)
    # Smoke output required by M0 acceptance
    print(f"MODE={config.mode.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
