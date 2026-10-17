"""Trade Journal — record and query every decision / fill / system event."""

from __future__ import annotations

from autotrader.journal.api import TradeJournal, open_trade_journal
from autotrader.journal.kill_switch import PersistentKillSwitch
from autotrader.journal.persist import (
    persist_execution_outcome,
    persist_risk_outcome,
    persist_signal,
)

__all__ = [
    "PersistentKillSwitch",
    "TradeJournal",
    "open_trade_journal",
    "persist_execution_outcome",
    "persist_risk_outcome",
    "persist_signal",
]
