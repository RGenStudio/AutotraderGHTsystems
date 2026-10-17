"""Shared execution types (paper / future MT5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ExecutionStatus(StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ApprovedOrder:
    """Order that already passed the Risk Engine."""

    symbol: str
    side: str  # long | short
    volume: float
    entry_price: float
    stop_price: float
    take_profit: float | None
    idempotency_key: str
    risk_pct: float


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    side: str
    volume: float
    entry_price: float
    ticket: str
    opened_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: ExecutionStatus
    ticket: str = ""
    message: str = ""
    idempotency_key: str = ""
