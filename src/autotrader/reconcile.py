"""Startup reconcile stub — mismatch pauses the engine via kill switch."""

from __future__ import annotations

from dataclasses import dataclass

from autotrader.execution.types import Position
from autotrader.kill_switch import KillSwitch


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    ok: bool
    paused: bool
    reason: str
    local_count: int
    remote_count: int
    mismatched_symbols: tuple[str, ...] = ()


def _position_fingerprint(positions: list[Position]) -> set[tuple[str, str, str]]:
    """Compare by symbol + side + ticket (stable enough for the stub)."""
    return {
        (p.symbol.upper(), p.side.lower(), p.ticket)
        for p in positions
    }


def reconcile_positions(
    *,
    local: list[Position],
    remote: list[Position],
    kill_switch: KillSwitch,
) -> ReconcileResult:
    """
    Compare local journal positions vs broker/demo backend.

    On mismatch: engage kill switch / pause until a human clears.
    Matching empty sets is OK (flat start).
    """
    local_fp = _position_fingerprint(local)
    remote_fp = _position_fingerprint(remote)

    if local_fp == remote_fp:
        return ReconcileResult(
            ok=True,
            paused=False,
            reason="ok",
            local_count=len(local),
            remote_count=len(remote),
        )

    local_symbols = {s for s, _, _ in local_fp}
    remote_symbols = {s for s, _, _ in remote_fp}
    mismatched = tuple(sorted(local_symbols.symmetric_difference(remote_symbols)))
    # Also flag ticket/side mismatches when symbol sets coincide
    if not mismatched and local_fp != remote_fp:
        mismatched = tuple(sorted(local_symbols | remote_symbols))

    kill_switch.engage("reconcile_mismatch")
    return ReconcileResult(
        ok=False,
        paused=True,
        reason="reconcile_mismatch",
        local_count=len(local),
        remote_count=len(remote),
        mismatched_symbols=mismatched,
    )
