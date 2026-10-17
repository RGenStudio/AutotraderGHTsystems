"""``python -m autotrader.paper_ab`` entry point."""

from __future__ import annotations

import sys

from autotrader.paper_ab.cli import main

if __name__ == "__main__":
    sys.exit(main())
