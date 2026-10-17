"""Execution layer — paper/demo stubs (no real MT5 order send in CI)."""

from autotrader.execution.factory import create_execution_backend, refuse_live_mode
from autotrader.execution.paper import PaperExecutionBackend
from autotrader.execution.protocol import ExecutionBackend
from autotrader.execution.types import (
    ApprovedOrder,
    ExecutionResult,
    ExecutionStatus,
    Position,
)

__all__ = [
    "ApprovedOrder",
    "ExecutionBackend",
    "ExecutionResult",
    "ExecutionStatus",
    "PaperExecutionBackend",
    "Position",
    "create_execution_backend",
    "refuse_live_mode",
]
