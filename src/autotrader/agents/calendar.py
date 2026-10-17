"""Economic calendar adapter for Agent 2 — URL feed + stub for tests."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

HIGH_IMPACT = frozenset({"high", "high-impact", "red"})


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One structured calendar row (no HTML scrape)."""

    time: datetime
    currency: str
    impact: str
    title: str = ""

    @property
    def is_high_impact(self) -> bool:
        return self.impact.strip().lower() in HIGH_IMPACT


class NewsCalendarProvider(Protocol):
    def fetch_events(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> list[CalendarEvent]: ...


@dataclass
class StubNewsCalendar:
    """In-memory / fixture calendar for unit tests (no network)."""

    events: list[CalendarEvent]

    def fetch_events(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> list[CalendarEvent]:
        since_a = _ensure_aware(since)
        until_a = _ensure_aware(until)
        return [e for e in self.events if since_a <= _ensure_aware(e.time) < until_a]


@dataclass
class UrlNewsCalendar:
    """
    GET ``NEWS_CALENDAR_URL`` expecting a JSON list of events.

    Accepted shapes per item:
      {"time": ISO8601, "currency": "USD", "impact": "high", "title": "..."}
    or ``datetime`` / ``event_time`` keys; impact may be ``High``.
    """

    url: str
    timeout_s: float = 15.0

    def fetch_events(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> list[CalendarEvent]:
        payload = self._get_json()
        items = _coerce_event_list(payload)
        since_a = _ensure_aware(since)
        until_a = _ensure_aware(until)
        out: list[CalendarEvent] = []
        for item in items:
            event = _parse_event(item)
            if event is None:
                continue
            t = _ensure_aware(event.time)
            if since_a <= t < until_a:
                out.append(event)
        return out

    def _get_json(self) -> Any:
        req = Request(self.url, headers={"Accept": "application/json", "User-Agent": "autotrader"})
        with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 — URL from config
            raw = resp.read().decode("utf-8")
        return json.loads(raw)


def create_news_calendar(
    *,
    url: str | None = None,
    stub: StubNewsCalendar | None = None,
) -> NewsCalendarProvider:
    """Prefer stub (tests); else URL adapter; else empty stub."""
    if stub is not None:
        return stub
    if url and url.strip():
        return UrlNewsCalendar(url=url.strip())
    return StubNewsCalendar(events=[])


def currencies_for_symbol(symbol: str) -> set[str]:
    """EURUSD → {EUR, USD}; USDJPY → {USD, JPY}."""
    s = symbol.strip().upper()
    if len(s) >= 6:
        return {s[:3], s[3:6]}
    return {s}


def high_impact_blackout(
    now: datetime,
    events: list[CalendarEvent],
    *,
    symbol: str,
    blackout_minutes: int = 30,
    currencies: set[str] | None = None,
) -> tuple[bool, list[CalendarEvent]]:
    """
    True when ``now`` is within ±blackout_minutes of a High-impact event
    whose currency intersects the symbol's pair (or configured set).
    """
    relevant = currencies or currencies_for_symbol(symbol)
    relevant = {c.upper() for c in relevant}
    window = timedelta(minutes=blackout_minutes)
    now_a = _ensure_aware(now)
    hits: list[CalendarEvent] = []
    for event in events:
        if not event.is_high_impact:
            continue
        if event.currency.strip().upper() not in relevant:
            continue
        delta = abs(_ensure_aware(event.time) - now_a)
        if delta <= window:
            hits.append(event)
    return (len(hits) > 0, hits)


def safe_fetch_around(
    provider: NewsCalendarProvider,
    now: datetime,
    *,
    pad_hours: int = 12,
) -> list[CalendarEvent]:
    """Fetch a padded window; on transport failure return [] and log."""
    now_a = _ensure_aware(now)
    since = now_a - timedelta(hours=pad_hours)
    until = now_a + timedelta(hours=pad_hours)
    try:
        return provider.fetch_events(since=since, until=until)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("News calendar fetch failed: %s", exc)
        return []


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_event_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("events", "data", "items", "calendar"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def _parse_event(item: dict[str, Any]) -> CalendarEvent | None:
    time_raw = item.get("time") or item.get("datetime") or item.get("event_time")
    currency = item.get("currency") or item.get("ccy") or item.get("country")
    impact = item.get("impact") or item.get("importance") or item.get("level") or ""
    title = str(item.get("title") or item.get("event") or item.get("name") or "")
    if time_raw is None or currency is None:
        return None
    try:
        when = _parse_time(time_raw)
    except (TypeError, ValueError):
        return None
    return CalendarEvent(
        time=when,
        currency=str(currency).strip().upper(),
        impact=str(impact).strip().lower(),
        title=title,
    )


def _parse_time(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return _ensure_aware(raw)
    text = str(raw).strip().replace("Z", "+00:00")
    return _ensure_aware(datetime.fromisoformat(text))
