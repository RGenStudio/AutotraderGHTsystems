"""M3 Risk Engine — pass + reject cases for every locked rule."""

from __future__ import annotations

from datetime import UTC, datetime

from autotrader.config import ActiveWindow, Mode
from autotrader.kill_switch import KillSwitch
from autotrader.risk import (
    CandidateOrder,
    OpenPositionView,
    RiskContext,
    RiskEngine,
    default_risk_limits,
)


def _engine(**kwargs: object) -> RiskEngine:
    return RiskEngine(limits=default_risk_limits(), **kwargs)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> CandidateOrder:
    base = dict(
        symbol="EURUSD",
        side="long",
        requested_risk_pct=0.5,
        stop_distance_price=0.0010,
        entry_price=1.1000,
        idempotency_key="ord-1",
    )
    base.update(overrides)
    return CandidateOrder(**base)  # type: ignore[arg-type]


def _ctx(**overrides: object) -> RiskContext:
    base = dict(
        equity=10_000.0,
        open_positions=(),
        daily_loss_pct=0.0,
        weekly_drawdown_pct=0.0,
        now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),  # Wed 15:00 UTC inside window
        mode=Mode.PAPER,
    )
    base.update(overrides)
    return RiskContext(**base)  # type: ignore[arg-type]


def test_approve_within_all_limits() -> None:
    decision = _engine().evaluate(_candidate(), _ctx())
    assert decision.allowed is True
    assert decision.reason == "ok"


def test_reject_requested_risk_above_cap_pass_boundary() -> None:
    eng = _engine()
    ok = eng.evaluate(_candidate(requested_risk_pct=0.5), _ctx())
    bad = eng.evaluate(_candidate(requested_risk_pct=0.51), _ctx())
    assert ok.allowed is True
    assert bad.allowed is False
    assert bad.reason == "requested_risk_above_cap"


def test_reject_max_daily_loss_pass_below() -> None:
    eng = _engine()
    ok = eng.evaluate(_candidate(), _ctx(daily_loss_pct=1.99))
    bad = eng.evaluate(_candidate(), _ctx(daily_loss_pct=2.0))
    assert ok.allowed is True
    assert bad.reason == "max_daily_loss"


def test_reject_max_weekly_drawdown_engages_kill_switch() -> None:
    ks = KillSwitch()
    eng = _engine(kill_switch=ks)
    ok = eng.evaluate(_candidate(), _ctx(weekly_drawdown_pct=4.99))
    bad = eng.evaluate(_candidate(idempotency_key="ord-2"), _ctx(weekly_drawdown_pct=5.0))
    assert ok.allowed is True
    assert bad.reason == "max_weekly_drawdown"
    assert ks.is_active() is True
    # subsequent cycle still blocked via kill switch
    again = eng.evaluate(_candidate(idempotency_key="ord-3"), _ctx(weekly_drawdown_pct=0.0))
    assert again.reason == "kill_switch_active"


def test_reject_max_open_positions_pass_one() -> None:
    eng = _engine()
    one = (
        OpenPositionView(symbol="EURUSD", side="long", ticket="1"),
    )
    two = (
        OpenPositionView(symbol="EURUSD", side="long", ticket="1"),
        OpenPositionView(symbol="USDJPY", side="short", ticket="2"),
    )
    ok = eng.evaluate(_candidate(symbol="USDJPY"), _ctx(open_positions=one))
    bad = eng.evaluate(_candidate(symbol="EURUSD"), _ctx(open_positions=two))
    assert ok.allowed is True
    assert bad.reason == "max_open_positions"


def test_reject_symbol_already_open() -> None:
    open_pos = (OpenPositionView(symbol="EURUSD", side="long", ticket="1"),)
    decision = _engine().evaluate(_candidate(symbol="EURUSD"), _ctx(open_positions=open_pos))
    assert decision.allowed is False
    assert decision.reason == "symbol_already_open"


def test_reject_kill_switch_every_cycle() -> None:
    ks = KillSwitch()
    ks.engage("manual")
    eng = _engine(kill_switch=ks)
    assert eng.check_kill_switch() is True
    decision = eng.evaluate(_candidate(), _ctx())
    assert decision.reason == "kill_switch_active"


def test_reject_outside_active_window_pass_inside() -> None:
    eng = _engine(active_window=ActiveWindow(start="12:00", end="21:00", weekdays_only=True))
    inside = eng.evaluate(
        _candidate(),
        _ctx(now=datetime(2026, 10, 14, 12, 0, tzinfo=UTC)),
    )
    outside = eng.evaluate(
        _candidate(idempotency_key="ord-out"),
        _ctx(now=datetime(2026, 10, 14, 21, 0, tzinfo=UTC)),
    )
    weekend = eng.evaluate(
        _candidate(idempotency_key="ord-wk"),
        _ctx(now=datetime(2026, 10, 17, 15, 0, tzinfo=UTC)),  # Saturday
    )
    assert inside.allowed is True
    assert outside.reason == "outside_active_window"
    assert weekend.reason == "outside_active_window"


def test_reject_bad_json_pass_valid_payload() -> None:
    eng = _engine()
    good = {
        "action": "enter",
        "symbol": "EURUSD",
        "side": "long",
        "requested_risk_pct": 0.4,
        "stop_distance_price": 0.001,
        "entry_price": 1.1,
        "idempotency_key": "json-1",
    }
    ok = eng.evaluate(None, _ctx(), raw_json=good)
    assert ok.allowed is True

    bad_cases = [
        None,
        "not-a-dict",
        [],
        {},  # missing fields
        {**good, "action": "explode"},
        {**good, "requested_risk_pct": -1},
        {**good, "symbol": ""},
    ]
    for i, raw in enumerate(bad_cases):
        decision = eng.evaluate(None, _ctx(), raw_json=raw)
        assert decision.allowed is False, f"case {i} should reject"
        assert decision.reason == "bad_json"


def test_decision_skip_from_json() -> None:
    payload = {
        "action": "skip",
        "symbol": "EURUSD",
        "side": "long",
        "requested_risk_pct": 0.4,
        "stop_distance_price": 0.001,
        "entry_price": 1.1,
        "idempotency_key": "skip-1",
    }
    decision = _engine().evaluate(None, _ctx(), raw_json=payload)
    assert decision.reason == "decision_skip"


def test_reject_live_mode_forbidden() -> None:
    decision = _engine().evaluate(_candidate(), _ctx(mode=Mode.LIVE))
    assert decision.allowed is False
    assert decision.reason == "live_mode_forbidden"


def test_reject_symbol_not_allowed() -> None:
    decision = _engine().evaluate(_candidate(symbol="XAUUSD"), _ctx())
    assert decision.reason == "symbol_not_allowed"


def test_reject_missing_candidate_and_idempotency() -> None:
    eng = _engine()
    assert eng.evaluate(None, _ctx()).reason == "missing_candidate"
    blank_key = eng.evaluate(_candidate(idempotency_key="  "), _ctx())
    assert blank_key.reason == "missing_idempotency_key"


def test_reject_invalid_prices_and_equity() -> None:
    eng = _engine()
    assert (
        eng.evaluate(_candidate(stop_distance_price=0), _ctx()).reason == "invalid_prices"
    )
    assert eng.evaluate(_candidate(), _ctx(equity=0)).reason == "invalid_equity"
