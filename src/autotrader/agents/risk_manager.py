"""Agent 3 — Risk Manager (proposes size/SL/TP; Risk Engine is authority)."""

from __future__ import annotations

from typing import Any

from autotrader.agents.base import AgentCallOutcome, run_structured_agent
from autotrader.agents.schemas import (
    NewsAnalysisOutput,
    RiskManagerOutput,
    TechnicalAnalysisOutput,
)
from autotrader.journal.api import TradeJournal
from autotrader.llm.client import LLMClient

AGENT_NAME = "risk_manager"

SYSTEM_PROMPT = """You are Agent 3 (Risk Manager) for a Forex system.
Propose risk_pct, stop_loss, and take_profit only. The code Risk Engine has final authority
and will reject proposals above project ceilings (default max 0.5% risk per trade).
Respond with JSON:
should_trade (bool), risk_pct (number > 0), stop_loss (number),
take_profit (number|null), reasoning (short string).
Do not invent new signals — only size/risk the candidate from context."""


class RiskManagerAgent:
    def __init__(
        self,
        client: LLMClient,
        *,
        model: str = "mock-mid",
        journal: TradeJournal | None = None,
        max_risk_pct: float = 0.5,
    ) -> None:
        self.client = client
        self.model = model
        self.journal = journal
        self.max_risk_pct = max_risk_pct

    def propose(
        self,
        context: dict[str, Any],
        *,
        technical: TechnicalAnalysisOutput | None,
        news: NewsAnalysisOutput | None,
        decision_id: int | None = None,
    ) -> AgentCallOutcome[RiskManagerOutput]:
        user_payload = {
            **context,
            "max_risk_pct_ceiling": self.max_risk_pct,
            "technical": technical.model_dump(mode="json") if technical else None,
            "news": news.model_dump(mode="json") if news else None,
        }
        return run_structured_agent(
            client=self.client,
            journal=self.journal,
            agent_name=AGENT_NAME,
            model=self.model,
            schema=RiskManagerOutput,
            system_prompt=SYSTEM_PROMPT,
            user_payload=user_payload,
            decision_id=decision_id,
        )
