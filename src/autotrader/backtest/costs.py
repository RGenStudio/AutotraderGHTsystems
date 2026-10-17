"""Configurable light simulation of spread, slippage, and fees."""

from __future__ import annotations

from dataclasses import dataclass

from autotrader.strategy.types import Side


@dataclass(frozen=True, slots=True)
class CostModel:
    """
    Round-trip cost model in price units (not pips).

    - ``spread``: full bid-ask width applied at entry (half each side conceptually).
    - ``slippage``: adverse price move on entry and on exit.
    - ``fee_per_trade``: flat commission deducted from PnL once per closed trade (price units).
    """

    spread: float = 0.00012  # ~1.2 pips EURUSD-style default
    slippage: float = 0.00005
    fee_per_trade: float = 0.0

    def apply_entry(self, price: float, side: Side) -> float:
        half_spread = self.spread / 2.0
        if side is Side.LONG:
            return price + half_spread + self.slippage
        return price - half_spread - self.slippage

    def apply_exit(self, price: float, side: Side) -> float:
        half_spread = self.spread / 2.0
        if side is Side.LONG:
            return price - half_spread - self.slippage
        return price + half_spread + self.slippage
