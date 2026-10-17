"""Wire Agents 1–4: bad JSON / LLM fail ⇒ do not trade; journal every call."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from autotrader.agents.calendar import NewsCalendarProvider
from autotrader.agents.decision_maker import DecisionMakerAgent
from autotrader.agents.news import NewsAgent
from autotrader.agents.risk_manager import RiskManagerAgent
from autotrader.agents.schemas import DecisionMakerOutput
from autotrader.agents.technical import TechnicalAnalystAgent
from autotrader.config import AppConfig, load_config
from autotrader.journal.api import TradeJournal
from autotrader.llm.client import LLMClient
from autotrader.llm.factory import create_llm_client


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Outcome of one agent cycle (pre-Risk Engine)."""

    trade_allowed: bool
    reason: str
    decision: DecisionMakerOutput | None = None
    risk_payload: dict[str, Any] | None = None
    agent_call_ids: tuple[int, ...] = ()
    technical: Any = None
    news: Any = None
    risk_manager: Any = None
    errors: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


class AgentPipeline:
    """
    Run Agents 1∥2 → 3 → 4 for a Strategy Engine candidate.

    Hard rules:
    - Agents 1 and 2 run in parallel when ``parallel_12`` is True (M6 default).
    - Any LLM / schema failure ⇒ ``trade_allowed=False`` (do not trade).
    - Agent 2 ``no_trade_news`` ⇒ skip Decision Maker enter (no trade).
    - Agent 4 invalid / skip ⇒ no trade.
    - Every call recorded via journal ``agent_calls`` (+ costs).
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        journal: TradeJournal | None = None,
        config: AppConfig | None = None,
        calendar: NewsCalendarProvider | None = None,
        calendar_url: str | None = None,
        parallel_12: bool = True,
    ) -> None:
        self.config = config or load_config()
        self.journal = journal
        self.parallel_12 = parallel_12
        models = self.config.llm.models
        self.technical = TechnicalAnalystAgent(
            client, model=models.technical, journal=journal
        )
        self.news = NewsAgent(
            client,
            model=models.news,
            journal=journal,
            calendar=calendar,
            news_config=self.config.news,
            calendar_url=calendar_url,
        )
        self.risk_manager = RiskManagerAgent(
            client,
            model=models.risk_manager,
            journal=journal,
            max_risk_pct=self.config.risk.max_risk_per_trade_pct,
        )
        self.decision_maker = DecisionMakerAgent(
            client, model=models.decision_maker, journal=journal
        )

    def run(
        self,
        context: dict[str, Any],
        *,
        now: datetime,
        symbol: str,
        idempotency_key: str = "",
        decision_id: int | None = None,
    ) -> PipelineResult:
        call_ids: list[int] = []
        errors: list[str] = []

        tech_out, news_out = self._run_agents_1_and_2(
            context, now=now, symbol=symbol, decision_id=decision_id
        )
        if tech_out.agent_call_id is not None:
            call_ids.append(tech_out.agent_call_id)
        if news_out.agent_call_id is not None:
            call_ids.append(news_out.agent_call_id)

        if not tech_out.ok:
            errors.append(f"technical: {tech_out.error or 'failed'}")
            return self._no_trade(
                "llm_or_schema_fail",
                call_ids,
                errors,
                technical=None,
                news=news_out.parsed if news_out.ok else None,
                risk_manager=None,
            )
        if not news_out.ok:
            errors.append(f"news: {news_out.error or 'failed'}")
            return self._no_trade(
                "llm_or_schema_fail",
                call_ids,
                errors,
                technical=tech_out.parsed,
                news=None,
                risk_manager=None,
            )

        assert tech_out.parsed is not None
        assert news_out.parsed is not None

        if news_out.parsed.no_trade_news:
            return PipelineResult(
                trade_allowed=False,
                reason="news_blackout",
                decision=None,
                risk_payload=None,
                agent_call_ids=tuple(call_ids),
                technical=tech_out.parsed,
                news=news_out.parsed,
                risk_manager=None,
                errors=(),
                meta={"no_trade_news": True, "parallel_12": self.parallel_12},
            )

        risk_out = self.risk_manager.propose(
            context,
            technical=tech_out.parsed,
            news=news_out.parsed,
            decision_id=decision_id,
        )
        if risk_out.agent_call_id is not None:
            call_ids.append(risk_out.agent_call_id)
        if not risk_out.ok:
            errors.append(f"risk_manager: {risk_out.error or 'failed'}")
            return self._no_trade(
                "llm_or_schema_fail",
                call_ids,
                errors,
                technical=tech_out.parsed,
                news=news_out.parsed,
                risk_manager=None,
            )

        assert risk_out.parsed is not None

        decide_out = self.decision_maker.decide(
            context,
            technical=tech_out.parsed,
            news=news_out.parsed,
            risk=risk_out.parsed,
            decision_id=decision_id,
        )
        if decide_out.agent_call_id is not None:
            call_ids.append(decide_out.agent_call_id)
        if not decide_out.ok or decide_out.parsed is None:
            errors.append(f"decision_maker: {decide_out.error or 'failed'}")
            return self._no_trade(
                "bad_json",
                call_ids,
                errors,
                technical=tech_out.parsed,
                news=news_out.parsed,
                risk_manager=risk_out.parsed,
            )

        decision = decide_out.parsed
        if idempotency_key and not decision.idempotency_key:
            decision = decision.model_copy(update={"idempotency_key": idempotency_key})

        if not decision.is_enter:
            return PipelineResult(
                trade_allowed=False,
                reason="decision_skip",
                decision=decision,
                risk_payload=decision.to_risk_payload(idempotency_key=idempotency_key),
                agent_call_ids=tuple(call_ids),
                technical=tech_out.parsed,
                news=news_out.parsed,
                risk_manager=risk_out.parsed,
                errors=(),
                meta={"parallel_12": self.parallel_12},
            )

        payload = decision.to_risk_payload(idempotency_key=idempotency_key)
        return PipelineResult(
            trade_allowed=True,
            reason="ok",
            decision=decision,
            risk_payload=payload,
            agent_call_ids=tuple(call_ids),
            technical=tech_out.parsed,
            news=news_out.parsed,
            risk_manager=risk_out.parsed,
            errors=(),
            meta={"parallel_12": self.parallel_12},
        )

    def _run_agents_1_and_2(
        self,
        context: dict[str, Any],
        *,
        now: datetime,
        symbol: str,
        decision_id: int | None,
    ) -> tuple[Any, Any]:
        """Run Technical + News in parallel (or sequentially when disabled)."""
        if not self.parallel_12:
            tech_out = self.technical.analyze(context, decision_id=decision_id)
            news_out = self.news.analyze(
                context, now=now, symbol=symbol, decision_id=decision_id
            )
            return tech_out, news_out

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent12") as pool:
            fut_tech = pool.submit(self.technical.analyze, context, decision_id=decision_id)
            fut_news = pool.submit(
                self.news.analyze,
                context,
                now=now,
                symbol=symbol,
                decision_id=decision_id,
            )
            return fut_tech.result(), fut_news.result()

    @staticmethod
    def _no_trade(
        reason: str,
        call_ids: list[int],
        errors: list[str],
        *,
        technical: Any,
        news: Any,
        risk_manager: Any,
    ) -> PipelineResult:
        return PipelineResult(
            trade_allowed=False,
            reason=reason,
            decision=None,
            risk_payload=None,
            agent_call_ids=tuple(call_ids),
            technical=technical,
            news=news,
            risk_manager=risk_manager,
            errors=tuple(errors),
        )


def build_agent_pipeline(
    *,
    journal: TradeJournal | None = None,
    force_mock: bool = True,
    calendar: NewsCalendarProvider | None = None,
    calendar_url: str | None = None,
    client: LLMClient | None = None,
    config: AppConfig | None = None,
    parallel_12: bool = True,
) -> AgentPipeline:
    """Factory used by tests / orchestrator (M6). Default = mock LLM."""
    cfg = config or load_config()
    llm = client or create_llm_client(force_mock=force_mock)
    return AgentPipeline(
        llm,
        journal=journal,
        config=cfg,
        calendar=calendar,
        calendar_url=calendar_url,
        parallel_12=parallel_12,
    )
