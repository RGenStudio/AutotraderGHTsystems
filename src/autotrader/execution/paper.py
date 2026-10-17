"""Paper / demo execution backend — in-memory fills, no broker I/O."""

from __future__ import annotations

from datetime import UTC, datetime

from autotrader.execution.types import (
    ApprovedOrder,
    ExecutionResult,
    ExecutionStatus,
    Position,
)


class PaperExecutionBackend:
    """
    Demo/paper fills kept in process memory.

    Idempotency: repeating the same ``idempotency_key`` returns the original
    fill as ``DUPLICATE`` and does **not** open a second position.
    """

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}  # ticket -> position
        self._by_key: dict[str, ExecutionResult] = {}
        self._ticket_seq = 0

    def send_order(self, order: ApprovedOrder) -> ExecutionResult:
        key = order.idempotency_key.strip()
        if not key:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                message="missing_idempotency_key",
                idempotency_key=key,
            )

        prior = self._by_key.get(key)
        if prior is not None:
            return ExecutionResult(
                status=ExecutionStatus.DUPLICATE,
                ticket=prior.ticket,
                message="idempotent_replay",
                idempotency_key=key,
            )

        if order.volume <= 0:
            result = ExecutionResult(
                status=ExecutionStatus.REJECTED,
                message="invalid_volume",
                idempotency_key=key,
            )
            self._by_key[key] = result
            return result

        self._ticket_seq += 1
        ticket = f"paper-{self._ticket_seq}"
        position = Position(
            symbol=order.symbol.upper(),
            side=order.side.lower(),
            volume=order.volume,
            entry_price=order.entry_price,
            ticket=ticket,
            opened_at=datetime.now(UTC),
        )
        self._positions[ticket] = position
        result = ExecutionResult(
            status=ExecutionStatus.FILLED,
            ticket=ticket,
            message="paper_fill",
            idempotency_key=key,
        )
        self._by_key[key] = result
        return result

    def list_open_positions(self) -> list[Position]:
        return list(self._positions.values())

    def close_all(self) -> None:
        self._positions.clear()

    def close_ticket(self, ticket: str) -> bool:
        return self._positions.pop(ticket, None) is not None
