"""Agent 2 calendar adapter + ±30min high-impact blackout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from autotrader.agents.calendar import (
    CalendarEvent,
    StubNewsCalendar,
    UrlNewsCalendar,
    create_news_calendar,
    currencies_for_symbol,
    high_impact_blackout,
)


def test_currencies_for_symbol() -> None:
    assert currencies_for_symbol("EURUSD") == {"EUR", "USD"}
    assert currencies_for_symbol("USDJPY") == {"USD", "JPY"}


def test_blackout_within_30_minutes() -> None:
    now = datetime(2026, 10, 17, 14, 0, tzinfo=UTC)
    events = [
        CalendarEvent(
            time=now + timedelta(minutes=20),
            currency="USD",
            impact="high",
            title="NFP",
        )
    ]
    active, hits = high_impact_blackout(
        now, events, symbol="EURUSD", blackout_minutes=30
    )
    assert active
    assert hits[0].title == "NFP"


def test_blackout_outside_window() -> None:
    now = datetime(2026, 10, 17, 14, 0, tzinfo=UTC)
    events = [
        CalendarEvent(
            time=now + timedelta(minutes=45),
            currency="USD",
            impact="high",
            title="NFP",
        )
    ]
    active, hits = high_impact_blackout(
        now, events, symbol="EURUSD", blackout_minutes=30
    )
    assert not active
    assert hits == []


def test_blackout_ignores_low_impact_and_other_ccy() -> None:
    now = datetime(2026, 10, 17, 14, 0, tzinfo=UTC)
    events = [
        CalendarEvent(time=now, currency="USD", impact="low", title="speech"),
        CalendarEvent(time=now, currency="GBP", impact="high", title="UK CPI"),
    ]
    active, _ = high_impact_blackout(now, events, symbol="EURUSD", blackout_minutes=30)
    assert not active


def test_stub_calendar_filters_window() -> None:
    t0 = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    cal = StubNewsCalendar(
        events=[
            CalendarEvent(time=t0, currency="EUR", impact="high", title="A"),
            CalendarEvent(
                time=t0 + timedelta(hours=5), currency="USD", impact="high", title="B"
            ),
        ]
    )
    got = cal.fetch_events(since=t0, until=t0 + timedelta(hours=1))
    assert len(got) == 1
    assert got[0].title == "A"


def test_create_news_calendar_prefers_stub() -> None:
    stub = StubNewsCalendar(events=[])
    assert create_news_calendar(stub=stub) is stub


def test_create_news_calendar_url() -> None:
    cal = create_news_calendar(url="https://example.com/calendar.json")
    assert isinstance(cal, UrlNewsCalendar)


def test_url_calendar_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import autotrader.agents.calendar as cal_mod

    payload = b"""[
      {"time": "2026-10-17T14:00:00+00:00", "currency": "USD",
       "impact": "High", "title": "CPI"}
    ]"""

    class _Resp:
        def read(self) -> bytes:
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(cal_mod, "urlopen", lambda *a, **k: _Resp())
    cal = UrlNewsCalendar(url="https://example.invalid/cal.json")
    events = cal.fetch_events(
        since=datetime(2026, 10, 17, 0, 0, tzinfo=UTC),
        until=datetime(2026, 10, 18, 0, 0, tzinfo=UTC),
    )
    assert len(events) == 1
    assert events[0].is_high_impact
    assert events[0].currency == "USD"
