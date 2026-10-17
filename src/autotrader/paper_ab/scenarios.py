"""Deterministic synthetic cycle fixtures for paper A/B (no live market required)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

AiOutcome = Literal["enter", "skip", "bad_json", "llm_fail"]


@dataclass(frozen=True, slots=True)
class SyntheticCycle:
    """
    One mock H1 cycle input shared by both A/B arms.

    ``pnl_r`` is the realized R multiple *if* the arm takes the trade (keyed by
    cycle so both arms see the same outcome for the same signal).
    """

    cycle_index: int
    now: datetime
    symbol: str
    has_signal: bool
    side: str = "long"
    entry_price: float = 1.0850
    stop_price: float = 1.0800
    take_profit: float | None = 1.0950
    atr: float = 0.0012
    strategy: str = "A"
    pnl_r: float = 1.0
    ai_outcome: AiOutcome = "enter"
    risk_pct: float = 0.5


def _stable_unit(seed: int, cycle_index: int, salt: str) -> float:
    """Deterministic float in [0, 1) from seed + cycle + salt."""
    digest = hashlib.sha256(f"{seed}:{cycle_index}:{salt}".encode()).hexdigest()
    return int(digest[:12], 16) / float(16**12)


def generate_synthetic_cycles(
    *,
    count: int,
    seed: int = 42,
    symbols: tuple[str, ...] = ("EURUSD", "USDJPY"),
    start: datetime | None = None,
    signal_rate: float = 0.55,
    bad_json_rate: float = 0.02,
    ai_skip_rate: float = 0.15,
    positive_bias: float = 0.55,
) -> list[SyntheticCycle]:
    """
    Build ``count`` synthetic cycles with reproducible signal / AI / R outcomes.

    Tuned so a short CI run can exercise metrics and gates without a multi-week
    live paper session. Pass rates are *approximate* (hash-driven).
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if not symbols:
        raise ValueError("symbols must be non-empty")

    anchor = start or datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    else:
        anchor = anchor.astimezone(UTC)

    cycles: list[SyntheticCycle] = []
    for i in range(count):
        # Advance ~1 H1 bar; skip weekends roughly (Fri evening → Mon)
        now = anchor + timedelta(hours=i)
        while now.weekday() >= 5:
            now += timedelta(hours=1)
            # keep advancing past weekend
            if now.weekday() < 5:
                break
        # Snap into a weekday active-window-ish hour if we drifted
        if now.weekday() >= 5:
            days_ahead = 7 - now.weekday()
            now = now + timedelta(days=days_ahead)
            now = now.replace(hour=12, minute=0, second=0, microsecond=0)

        symbol = symbols[i % len(symbols)]
        pip = 0.01 if "JPY" in symbol.upper() else 0.0001
        base = 148.50 if "JPY" in symbol.upper() else 1.0850
        has_signal = _stable_unit(seed, i, "signal") < signal_rate

        side = "long" if _stable_unit(seed, i, "side") < 0.55 else "short"
        entry = base + (_stable_unit(seed, i, "entry") - 0.5) * pip * 40
        stop_dist = pip * (8 + int(_stable_unit(seed, i, "stop") * 12))
        if side == "long":
            stop = entry - stop_dist
            tp = entry + stop_dist * 1.5
        else:
            stop = entry + stop_dist
            tp = entry - stop_dist * 1.5

        # R outcome: mix of wins/losses with slight positive bias
        u = _stable_unit(seed, i, "pnl")
        if u < positive_bias:
            pnl_r = 0.8 + _stable_unit(seed, i, "win_mag") * 1.4  # ~0.8..2.2R
        else:
            pnl_r = -(0.7 + _stable_unit(seed, i, "loss_mag") * 0.5)  # ~-0.7..-1.2R

        # AI outcomes (Agent 4 path)
        u_ai = _stable_unit(seed, i, "ai")
        if u_ai < bad_json_rate:
            ai_outcome: AiOutcome = "bad_json"
        elif u_ai < bad_json_rate + ai_skip_rate:
            ai_outcome = "skip"
        else:
            ai_outcome = "enter"

        strategy = ("A", "B", "C")[int(_stable_unit(seed, i, "strat") * 3) % 3]
        cycles.append(
            SyntheticCycle(
                cycle_index=i,
                now=now,
                symbol=symbol,
                has_signal=has_signal,
                side=side,
                entry_price=round(entry, 5),
                stop_price=round(stop, 5),
                take_profit=round(tp, 5),
                atr=round(stop_dist * 0.6, 5),
                strategy=strategy,
                pnl_r=round(pnl_r, 4),
                ai_outcome=ai_outcome,
                risk_pct=0.5,
            )
        )
    return cycles


def load_cycles_fixture(path: Path) -> list[SyntheticCycle]:
    """Load cycles from a JSON fixture (tests / reproducible demos)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("fixture must be a JSON list of cycle objects")
    out: list[SyntheticCycle] = []
    for item in raw:
        out.append(_cycle_from_dict(item))
    return out


def _cycle_from_dict(item: dict[str, Any]) -> SyntheticCycle:
    now_raw = item["now"]
    now = datetime.fromisoformat(now_raw)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    tp = item.get("take_profit")
    return SyntheticCycle(
        cycle_index=int(item["cycle_index"]),
        now=now,
        symbol=str(item["symbol"]),
        has_signal=bool(item["has_signal"]),
        side=str(item.get("side", "long")),
        entry_price=float(item.get("entry_price", 1.085)),
        stop_price=float(item.get("stop_price", 1.08)),
        take_profit=float(tp) if tp is not None else None,
        atr=float(item.get("atr", 0.001)),
        strategy=str(item.get("strategy", "A")),
        pnl_r=float(item.get("pnl_r", 1.0)),
        ai_outcome=item.get("ai_outcome", "enter"),  # type: ignore[arg-type]
        risk_pct=float(item.get("risk_pct", 0.5)),
    )


def cycles_to_dicts(cycles: list[SyntheticCycle]) -> list[dict[str, Any]]:
    """Serialize cycles for fixtures / debugging."""
    rows: list[dict[str, Any]] = []
    for c in cycles:
        rows.append(
            {
                "cycle_index": c.cycle_index,
                "now": c.now.isoformat(),
                "symbol": c.symbol,
                "has_signal": c.has_signal,
                "side": c.side,
                "entry_price": c.entry_price,
                "stop_price": c.stop_price,
                "take_profit": c.take_profit,
                "atr": c.atr,
                "strategy": c.strategy,
                "pnl_r": c.pnl_r,
                "ai_outcome": c.ai_outcome,
                "risk_pct": c.risk_pct,
            }
        )
    return rows
