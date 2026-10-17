"""Execution backend protocol — paper now, MT5 send later on Windows."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from autotrader.execution.types import ApprovedOrder, ExecutionResult, Position


@runtime_checkable
class ExecutionBackend(Protocol):
    """
    Order-send interface.

    Implementations must honor ``ApprovedOrder.idempotency_key`` so retries
    never create duplicate broker sends.
    """

    def send_order(self, order: ApprovedOrder) -> ExecutionResult:
        """Submit (or paper-fill) an approved order."""
        ...

    def list_open_positions(self) -> list[Position]:
        """Return currently open positions known to this backend."""
        ...

    def close_all(self) -> None:
        """Flatten all open positions (paper/demo helper)."""
        ...
