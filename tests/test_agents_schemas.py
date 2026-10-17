"""Agent 1–4 pydantic schemas — invalid ⇒ reject."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autotrader.agents.schemas import (
    DecisionMakerOutput,
    NewsAnalysisOutput,
    RiskManagerOutput,
    TechnicalAnalysisOutput,
)


def test_technical_rejects_size_fields() -> None:
    with pytest.raises(ValidationError):
        TechnicalAnalysisOutput.model_validate(
            {
                "direction": "long",
                "confidence": 80,
                "structure_supports_signal": True,
                "reasoning": "ok",
                "risk_pct": 0.5,
            }
        )


def test_technical_ok() -> None:
    out = TechnicalAnalysisOutput(
        direction="long",
        confidence=72,
        structure_supports_signal=True,
        key_levels=[1.08, 1.09],
        reasoning="H4 trend aligned",
    )
    assert out.direction == "long"


def test_news_schema() -> None:
    out = NewsAnalysisOutput(
        bias="neutral",
        impact_level="high",
        no_trade_news=True,
        reasoning="NFP within window",
        blackout_events=["NFP"],
    )
    assert out.no_trade_news


def test_risk_manager_schema() -> None:
    out = RiskManagerOutput(
        should_trade=True,
        risk_pct=0.5,
        stop_loss=1.081,
        take_profit=1.093,
        reasoning="within cap",
    )
    assert out.risk_pct == 0.5


def test_decision_maker_enter_long_maps_to_risk_payload() -> None:
    out = DecisionMakerOutput(
        action="enter_long",
        symbol="eurusd",
        risk_pct=0.5,
        stop_loss=1.0810,
        take_profit=1.0930,
        entry_price=1.0850,
        confidence=68,
        reasoning="aligned",
        conflicts_noted=["Agent 2 quiet"],
        idempotency_key="k1",
    )
    assert out.is_enter
    assert out.side == "long"
    assert out.stop_distance_price == pytest.approx(0.004)
    payload = out.to_risk_payload()
    assert payload["action"] == "enter"
    assert payload["side"] == "long"
    assert payload["symbol"] == "EURUSD"
    assert payload["requested_risk_pct"] == 0.5


def test_decision_maker_skip() -> None:
    out = DecisionMakerOutput(
        action="hold",
        symbol="USDJPY",
        confidence=20,
        reasoning="conflict",
    )
    assert not out.is_enter
    assert out.risk_action == "skip"


def test_decision_maker_invalid_action() -> None:
    with pytest.raises(ValidationError):
        DecisionMakerOutput(
            action="yolo",
            symbol="EURUSD",
            confidence=50,
            reasoning="nope",
        )


def test_decision_maker_enter_requires_prices() -> None:
    with pytest.raises(ValidationError):
        DecisionMakerOutput(
            action="enter_long",
            symbol="EURUSD",
            confidence=50,
            reasoning="missing prices",
        )
