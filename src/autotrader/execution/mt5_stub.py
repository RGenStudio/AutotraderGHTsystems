"""
MT5 order-send stub behind the ExecutionBackend protocol.

Real ``order_send`` stays Windows-only and is **not** called from CI.
This stub exists so later wiring can swap in a live MT5 adapter without
changing Risk Engine / orchestrator call sites.
"""

from __future__ import annotations

from autotrader.execution.types import ApprovedOrder, ExecutionResult, ExecutionStatus, Position


class MT5ExecutionStub:
    """
    Placeholder MT5 execution backend.

    Never performs a real MetaTrader5 ``order_send``. CI and paper phase must
    use :class:`~autotrader.execution.paper.PaperExecutionBackend` instead.
    """

    def send_order(self, order: ApprovedOrder) -> ExecutionResult:
        _ = order
        return ExecutionResult(
            status=ExecutionStatus.ERROR,
            message="mt5_order_send_not_implemented_use_paper",
            idempotency_key=order.idempotency_key,
        )

    def list_open_positions(self) -> list[Position]:
        return []

    def close_all(self) -> None:
        return None
