"""Agent 2 — News & calendar (high-impact no-trade flag)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from autotrader.agents.base import AgentCallOutcome, run_structured_agent
from autotrader.agents.calendar import (
    CalendarEvent,
    NewsCalendarProvider,
    StubNewsCalendar,
    create_news_calendar,
    currencies_for_symbol,
    high_impact_blackout,
    safe_fetch_around,
)
from autotrader.agents.schemas import NewsAnalysisOutput
from autotrader.config import NewsConfig
from autotrader.journal.api import TradeJournal
from autotrader.llm.client import LLMClient

AGENT_NAME = "news_analyst"

SYSTEM_PROMPT = """You are Agent 2 (News & Sentiment Analyst) for a Forex system.
Use ONLY the calendar/events supplied in the user JSON — do not invent news from memory.
Respond with JSON only:
bias (positive|negative|neutral), impact_level (low|medium|high),
no_trade_news (bool), reasoning (short), blackout_events (string array of titles).
If the code already marked blackout_active=true, set no_trade_news=true."""


class NewsAgent:
    """
    Calendar + high-impact blackout (±N minutes).

    Sentiment from free-form news is deferred; MVP = calendar flag.
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        model: str = "mock-cheap",
        journal: TradeJournal | None = None,
        calendar: NewsCalendarProvider | None = None,
        news_config: NewsConfig | None = None,
        calendar_url: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.journal = journal
        self.news_config = news_config or NewsConfig()
        self.calendar = calendar or create_news_calendar(url=calendar_url)

    def analyze(
        self,
        context: dict[str, Any],
        *,
        now: datetime,
        symbol: str,
        decision_id: int | None = None,
    ) -> AgentCallOutcome[NewsAnalysisOutput]:
        events = safe_fetch_around(self.calendar, now)
        relevant = currencies_for_symbol(symbol) & {
            c.upper() for c in self.news_config.high_impact_currencies
        }
        in_blackout, hits = high_impact_blackout(
            now,
            events,
            symbol=symbol,
            blackout_minutes=self.news_config.blackout_minutes,
            currencies=relevant or currencies_for_symbol(symbol),
        )
        # Code authority for the blackout window; LLM only explains / may agree.
        user_payload = {
            **context,
            "symbol": symbol,
            "now_utc": now.isoformat(),
            "blackout_minutes": self.news_config.blackout_minutes,
            "blackout_active": in_blackout,
            "calendar_events": [_event_dict(e) for e in events],
            "blackout_hits": [_event_dict(e) for e in hits],
        }
        outcome = run_structured_agent(
            client=self.client,
            journal=self.journal,
            agent_name=AGENT_NAME,
            model=self.model,
            schema=NewsAnalysisOutput,
            system_prompt=SYSTEM_PROMPT,
            user_payload=user_payload,
            decision_id=decision_id,
        )
        if outcome.ok and outcome.parsed is not None and in_blackout:
            # Enforce code blackout even if the model forgets the flag.
            from autotrader.llm.client import LLMResult

            forced = outcome.parsed.model_copy(
                update={
                    "no_trade_news": True,
                    "impact_level": "high",
                    "blackout_events": [
                        *(outcome.parsed.blackout_events or []),
                        *[h.title or h.currency for h in hits],
                    ],
                }
            )
            return AgentCallOutcome(
                agent_name=outcome.agent_name,
                result=LLMResult(
                    success=True,
                    parsed=forced,
                    raw_text=outcome.result.raw_text,
                    usage=outcome.result.usage,
                    error="",
                    agent_call_id=outcome.result.agent_call_id,
                ),
                agent_call_id=outcome.agent_call_id,
            )
        return outcome


def stub_calendar_with(events: list[CalendarEvent]) -> StubNewsCalendar:
    return StubNewsCalendar(events=events)


def _event_dict(event: CalendarEvent) -> dict[str, Any]:
    return {
        "time": event.time.isoformat(),
        "currency": event.currency,
        "impact": event.impact,
        "title": event.title,
        "high_impact": event.is_high_impact,
    }
