"""Shared types for the paper A/B harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ArmName(StrEnum):
    RULES_ONLY = "rules_only"
    RULES_PLUS_AI = "rules_plus_ai"


@dataclass(frozen=True, slots=True)
class ClosedPaperTrade:
    """One synthetic closed trade attributed to an A/B arm."""

    cycle_index: int
    symbol: str
    side: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_price: float
    pnl_r: float
    pnl: float
    reason: str
    arm: ArmName
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArmMetrics:
    """Aggregate metrics for one A/B arm."""

    arm: ArmName
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    reward_risk: float
    expectancy_r: float
    net_pnl: float
    net_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    equity_end: float
    starting_equity: float
    agent4_calls: int = 0
    bad_json_count: int = 0
    bad_json_rate: float = 0.0
    cycles_seen: int = 0
    signals_seen: int = 0
    entries_approved: int = 0
    entries_rejected: int = 0
    calendar_weeks: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["arm"] = self.arm.value
        return raw

    def summary_lines(self) -> list[str]:
        return [
            f"arm={self.arm.value}",
            f"trades={self.trades}",
            f"expectancy_R={self.expectancy_r:.4f}",
            f"max_DD_pct={self.max_drawdown_pct * 100:.2f}%",
            f"net_return_pct={self.net_return_pct * 100:.2f}%",
            f"R:R={self.reward_risk:.3f}",
            f"bad_JSON_rate={self.bad_json_rate:.2%} ({self.bad_json_count}/{self.agent4_calls})",
            f"equity_end={self.equity_end:.2f}",
        ]


@dataclass(frozen=True, slots=True)
class AbRunResult:
    """Full paper A/B run across one or both arms."""

    ab_mode: str
    cycles: int
    seed: int
    started_at: datetime
    finished_at: datetime
    arms: dict[str, ArmMetrics]
    trades_by_arm: dict[str, list[ClosedPaperTrade]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def arm(self, name: ArmName | str) -> ArmMetrics | None:
        key = name.value if isinstance(name, ArmName) else name
        return self.arms.get(key)
