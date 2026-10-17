"""M5 Agents 1–4 pipeline — mocked LLM; bad JSON / fail ⇒ no trade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from autotrader.agents.calendar import CalendarEvent, StubNewsCalendar
from autotrader.agents.pipeline import AgentPipeline, build_agent_pipeline
from autotrader.agents.schemas import DecisionMakerOutput
from autotrader.journal import open_trade_journal
from autotrader.llm import LLMClient, MockLLMBackend
from autotrader.risk import RiskContext, RiskEngine, default_risk_limits


def _tech() -> dict:
    return {
        "direction": "long",
        "confidence": 75,
        "structure_supports_signal": True,
        "key_levels": [1.08, 1.09],
        "reasoning": "H4 uptrend supports long",
    }


def _news(*, no_trade: bool = False) -> dict:
    return {
        "bias": "neutral",
        "impact_level": "low" if not no_trade else "high",
        "no_trade_news": no_trade,
        "reasoning": "quiet calendar" if not no_trade else "NFP blackout",
        "blackout_events": [] if not no_trade else ["NFP"],
    }


def _risk() -> dict:
    return {
        "should_trade": True,
        "risk_pct": 0.5,
        "stop_loss": 1.0810,
        "take_profit": 1.0930,
        "reasoning": "0.5% within ceiling",
    }


def _decision(*, action: str = "enter_long") -> dict:
    base = {
        "action": action,
        "symbol": "EURUSD",
        "risk_pct": 0.5,
        "stop_loss": 1.0810,
        "take_profit": 1.0930,
        "entry_price": 1.0850,
        "confidence": 68,
        "reasoning": "Agents aligned",
        "conflicts_noted": [],
        "idempotency_key": "sig-1",
    }
    if action in {"skip", "hold"}:
        return {
            "action": action,
            "symbol": "EURUSD",
            "confidence": 20,
            "reasoning": "skip",
            "conflicts_noted": [],
        }
    return base


@pytest.fixture
def journal(tmp_path: Path):
    return open_trade_journal(f"sqlite:///{tmp_path / 'agents.db'}")


def _pipeline_with_queue(
    journal,
    *responses: object,
    calendar: StubNewsCalendar | None = None,
) -> AgentPipeline:
    backend = MockLLMBackend()
    backend.enqueue(*responses)
    client = LLMClient(backend, timeout_s=5)
    return AgentPipeline(
        client,
        journal=journal,
        calendar=calendar or StubNewsCalendar(events=[]),
    )


def test_happy_path_enter_and_risk_engine(journal) -> None:
    pipe = _pipeline_with_queue(journal, _tech(), _news(), _risk(), _decision())
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    result = pipe.run(
        {
            "symbol": "EURUSD",
            "side": "long",
            "entry_price": 1.0850,
            "strategy": "A",
        },
        now=now,
        symbol="EURUSD",
        idempotency_key="sig-1",
    )
    assert result.trade_allowed
    assert result.reason == "ok"
    assert isinstance(result.decision, DecisionMakerOutput)
    assert result.risk_payload is not None
    assert len(result.agent_call_ids) == 4

    # Journal recorded all four agents
    calls = journal.query_agent_calls()
    assert len(calls) == 4
    names = [c.agent_name for c in calls]
    assert names == [
        "technical_analyst",
        "news_analyst",
        "risk_manager",
        "decision_maker",
    ]
    assert all(c.success for c in calls)

    # Risk Engine accepts the payload
    engine = RiskEngine(limits=default_risk_limits())
    decision = engine.evaluate(
        None,
        RiskContext(equity=10_000, now=now),
        raw_json=result.risk_payload,
    )
    assert decision.allowed


def test_bad_json_from_agent4_no_trade(journal) -> None:
    pipe = _pipeline_with_queue(
        journal, _tech(), _news(), _risk(), "<<<not-json>>>"
    )
    result = pipe.run(
        {"symbol": "EURUSD"},
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
        symbol="EURUSD",
    )
    assert not result.trade_allowed
    assert result.reason == "bad_json"
    calls = journal.query_agent_calls(agent_name="decision_maker")
    assert len(calls) == 1
    assert calls[0].success is False


def test_llm_fail_on_agent1_no_trade(journal) -> None:
    backend = MockLLMBackend()
    backend.fail_with = RuntimeError("provider down")
    pipe = AgentPipeline(
        LLMClient(backend),
        journal=journal,
        calendar=StubNewsCalendar(events=[]),
    )
    result = pipe.run(
        {"symbol": "EURUSD"},
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
        symbol="EURUSD",
    )
    assert not result.trade_allowed
    assert result.reason == "llm_or_schema_fail"
    calls = journal.query_agent_calls()
    assert len(calls) == 1
    assert calls[0].success is False


def test_news_blackout_blocks_trade(journal) -> None:
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    cal = StubNewsCalendar(
        events=[
            CalendarEvent(
                time=now + timedelta(minutes=10),
                currency="USD",
                impact="high",
                title="FOMC",
            )
        ]
    )
    # Even if LLM says no_trade_news=false, code blackout forces True.
    pipe = _pipeline_with_queue(
        journal,
        _tech(),
        _news(no_trade=False),
        calendar=cal,
    )
    result = pipe.run(
        {"symbol": "EURUSD"},
        now=now,
        symbol="EURUSD",
    )
    assert not result.trade_allowed
    assert result.reason == "news_blackout"
    assert result.news is not None
    assert result.news.no_trade_news is True
    # Agents 3–4 not called
    assert len(result.agent_call_ids) == 2


def test_decision_skip(journal) -> None:
    pipe = _pipeline_with_queue(
        journal, _tech(), _news(), _risk(), _decision(action="skip")
    )
    result = pipe.run(
        {"symbol": "EURUSD"},
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
        symbol="EURUSD",
    )
    assert not result.trade_allowed
    assert result.reason == "decision_skip"


def test_invalid_schema_agent3_no_trade(journal) -> None:
    pipe = _pipeline_with_queue(
        journal,
        _tech(),
        _news(),
        {"should_trade": True, "risk_pct": -1, "stop_loss": 1.0, "reasoning": "bad"},
    )
    result = pipe.run(
        {"symbol": "EURUSD"},
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
        symbol="EURUSD",
    )
    assert not result.trade_allowed
    assert result.reason == "llm_or_schema_fail"


def test_build_agent_pipeline_mock_default(journal) -> None:
    pipe = build_agent_pipeline(journal=journal, force_mock=True)
    assert isinstance(pipe, AgentPipeline)


def test_costs_recorded_for_agent_calls(journal) -> None:
    pipe = _pipeline_with_queue(journal, _tech(), _news(), _risk(), _decision())
    pipe.run(
        {"symbol": "EURUSD", "entry_price": 1.085},
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
        symbol="EURUSD",
        idempotency_key="sig-cost",
    )
    calls = journal.query_agent_calls()
    assert len(calls) == 4
    # Each successful call should have a linked cost row via record_cost
    from sqlalchemy import select

    from autotrader.db.models import CostRow

    with journal._session_factory() as session:
        costs = list(session.scalars(select(CostRow)).all())
    assert len(costs) >= 4
    assert all(c.kind == "llm_api" for c in costs)
