"""Allow ``python -m autotrader.backtest``."""

from __future__ import annotations

import sys

from autotrader.backtest.cli import main

if __name__ == "__main__":
    sys.exit(main())
