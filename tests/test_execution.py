"""M3 paper execution stub — idempotency, no real MT5 send."""

from __future__ import annotations

import pytest

from autotrader.config import Mode
from autotrader.execution import (
    ApprovedOrder,
    ExecutionStatus,
    PaperExecutionBackend,
    create_execution_backend,
    refuse_live_mode,
)
from autotrader.execution.factory import LiveModeForbiddenError
from autotrader.execution.mt5_stub import MT5ExecutionStub


def _order(**overrides: object) -> ApprovedOrder:
    base = dict(
        symbol="EURUSD",
        side="long",
        volume=0.1,
        entry_price=1.1000,
        stop_price=1.0950,
        take_profit=None,
        idempotency_key="idem-1",
        risk_pct=0.5,
    )
    base.update(overrides)
    return ApprovedOrder(**base)  # type: ignore[arg-type]


def test_paper_fill_and_list_positions() -> None:
    backend = PaperExecutionBackend()
    result = backend.send_order(_order())
    assert result.status == ExecutionStatus.FILLED
    assert result.ticket.startswith("paper-")
    positions = backend.list_open_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "EURUSD"


def test_idempotency_no_duplicate_send() -> None:
    backend = PaperExecutionBackend()
    first = backend.send_order(_order(idempotency_key="same-key"))
    second = backend.send_order(_order(idempotency_key="same-key"))
    assert first.status == ExecutionStatus.FILLED
    assert second.status == ExecutionStatus.DUPLICATE
    assert second.ticket == first.ticket
    assert len(backend.list_open_positions()) == 1


def test_paper_rejects_missing_key_and_bad_volume() -> None:
    backend = PaperExecutionBackend()
    missing = backend.send_order(_order(idempotency_key=""))
    bad_vol = backend.send_order(_order(idempotency_key="v0", volume=0))
    assert missing.status == ExecutionStatus.REJECTED
    assert bad_vol.status == ExecutionStatus.REJECTED


def test_factory_defaults_to_paper() -> None:
    backend = create_execution_backend(mode=Mode.PAPER)
    assert isinstance(backend, PaperExecutionBackend)


def test_factory_mt5_stub_does_not_send() -> None:
    stub = create_execution_backend(mode=Mode.PAPER, backend="mt5_stub")
    assert isinstance(stub, MT5ExecutionStub)
    result = stub.send_order(_order())
    assert result.status == ExecutionStatus.ERROR
    assert "not_implemented" in result.message


def test_factory_refuses_live_mode() -> None:
    with pytest.raises(LiveModeForbiddenError):
        create_execution_backend(mode=Mode.LIVE)
    with pytest.raises(LiveModeForbiddenError):
        refuse_live_mode(Mode.LIVE)


def test_factory_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown execution backend"):
        create_execution_backend(mode=Mode.PAPER, backend="broker_x")
