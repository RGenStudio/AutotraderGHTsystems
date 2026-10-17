"""Select execution backend — paper by default; live explicitly refused."""

from __future__ import annotations

import logging

from autotrader.config import Mode
from autotrader.execution.mt5_stub import MT5ExecutionStub
from autotrader.execution.paper import PaperExecutionBackend
from autotrader.execution.protocol import ExecutionBackend

logger = logging.getLogger(__name__)


class LiveModeForbiddenError(RuntimeError):
    """Raised when code attempts to enable live execution in this phase."""


def refuse_live_mode(mode: Mode) -> None:
    """
    Hard guard: live trading must not be enabled accidentally.

    Call from factories, CLI, and tests. ``MODE=live`` is a hard error until
    §13 pass + explicit human approval.
    """
    if mode == Mode.LIVE:
        raise LiveModeForbiddenError(
            "MODE=live is forbidden in this phase (paper/demo only). "
            "Unset MODE or set MODE=paper."
        )


def create_execution_backend(
    *,
    mode: Mode = Mode.PAPER,
    backend: str = "paper",
) -> ExecutionBackend:
    """
    Build an execution backend for the current mode.

    - Default / paper / backtest → :class:`PaperExecutionBackend` (no MT5 I/O).
    - ``backend="mt5_stub"`` → :class:`MT5ExecutionStub` (still no real send).
    - ``mode=live`` → always raises :class:`LiveModeForbiddenError`.
    """
    refuse_live_mode(mode)

    if backend == "mt5_stub":
        logger.info("Using MT5 execution stub (no real order_send)")
        return MT5ExecutionStub()

    if backend != "paper":
        raise ValueError(f"unknown execution backend: {backend!r} (use 'paper' or 'mt5_stub')")

    logger.info("Using paper execution backend (mode=%s)", mode.value)
    return PaperExecutionBackend()
