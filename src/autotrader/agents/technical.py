"""Agent 1 — Technical Analyst (cheap model slot)."""

from __future__ import annotations

from typing import Any

from autotrader.agents.base import AgentCallOutcome, run_structured_agent
from autotrader.agents.schemas import TechnicalAnalysisOutput
from autotrader.journal.api import TradeJournal
from autotrader.llm.client import LLMClient

AGENT_NAME = "technical_analyst"

SYSTEM_PROMPT = """You are Agent 1 (Technical Analyst) for a Forex system.
Decide whether price structure (support/resistance, H4 trend) supports the
Strategy Engine signal. Respond with JSON only matching the schema:
direction (long|short|neutral), confidence (0-100), structure_supports_signal (bool),
key_levels (number array), reasoning (short string).
Do NOT propose position size, stop loss, take profit, or order actions."""


class TechnicalAnalystAgent:
    """Cheap-slot agent: structure vs signal; never sizes or orders."""

    def __init__(
        self,
        client: LLMClient,
        *,
        model: str = "mock-cheap",
        journal: TradeJournal | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.journal = journal

    def analyze(
        self,
        context: dict[str, Any],
        *,
        decision_id: int | None = None,
    ) -> AgentCallOutcome[TechnicalAnalysisOutput]:
        return run_structured_agent(
            client=self.client,
            journal=self.journal,
            agent_name=AGENT_NAME,
            model=self.model,
            schema=TechnicalAnalysisOutput,
            system_prompt=SYSTEM_PROMPT,
            user_payload=context,
            decision_id=decision_id,
        )
