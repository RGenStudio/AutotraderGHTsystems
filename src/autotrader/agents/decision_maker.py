"""Agent 4 — Decision Maker (final JSON action; invalid schema ⇒ no trade)."""

from __future__ import annotations

from typing import Any

from autotrader.agents.base import AgentCallOutcome, run_structured_agent
from autotrader.agents.schemas import (
    DecisionMakerOutput,
    NewsAnalysisOutput,
    RiskManagerOutput,
    TechnicalAnalysisOutput,
)
from autotrader.journal.api import TradeJournal
from autotrader.llm.client import LLMClient

AGENT_NAME = "decision_maker"

SYSTEM_PROMPT = """You are Agent 4 (Decision Maker) for a Forex system.
Weigh Agents 1–3 and output a final JSON action. Schema fields:
action (enter_long|enter_short|skip|hold), symbol, side (optional),
risk_pct, stop_loss, take_profit, entry_price, confidence (0-100),
reasoning, conflicts_noted (string array), idempotency_key (optional).
If news no_trade_news is true, or technical structure does not support the signal,
prefer skip. Never invent symbols outside the candidate context."""


class DecisionMakerAgent:
    def __init__(
        self,
        client: LLMClient,
        *,
        model: str = "mock-strong",
        journal: TradeJournal | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.journal = journal

    def decide(
        self,
        context: dict[str, Any],
        *,
        technical: TechnicalAnalysisOutput | None,
        news: NewsAnalysisOutput | None,
        risk: RiskManagerOutput | None,
        decision_id: int | None = None,
    ) -> AgentCallOutcome[DecisionMakerOutput]:
        user_payload = {
            **context,
            "technical": technical.model_dump(mode="json") if technical else None,
            "news": news.model_dump(mode="json") if news else None,
            "risk_manager": risk.model_dump(mode="json") if risk else None,
        }
        return run_structured_agent(
            client=self.client,
            journal=self.journal,
            agent_name=AGENT_NAME,
            model=self.model,
            schema=DecisionMakerOutput,
            system_prompt=SYSTEM_PROMPT,
            user_payload=user_payload,
            decision_id=decision_id,
        )
