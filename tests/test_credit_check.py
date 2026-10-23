"""API credit low-alert — mocked HTTP, no real keys, cooldown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from autotrader.config import ApiCreditConfig, AppConfig, EnvSettings
from autotrader.llm.credit_check import (
    ApiCreditMonitor,
    redact_secrets,
)
from autotrader.telegram import NullTelegramNotifier


class _RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        _ = parse_mode
        self.messages.append(text)
        return True


def test_redact_secrets_masks_bearer_and_sk() -> None:
    raw = "Authorization: Bearer sk-abc123XYZ_secret and sk-proj-ABCDEFGH12345678"
    out = redact_secrets(raw)
    assert "sk-abc123XYZ_secret" not in out
    assert "Bearer ***" in out or "sk-***" in out


def test_openai_manual_env_triggers_alert_once_per_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env = EnvSettings(
        openai_credit_usd=0.5,
        api_credit_warn_usd=1.0,
    )
    notifier = _RecordingNotifier()
    clock_times = [
        datetime(2026, 10, 23, 8, 0, tzinfo=UTC),
        datetime(2026, 10, 23, 9, 0, tzinfo=UTC),  # within 6h
        datetime(2026, 10, 23, 15, 0, tzinfo=UTC),  # after 6h
    ]
    idx = {"i": 0}

    def _clock() -> datetime:
        t = clock_times[min(idx["i"], len(clock_times) - 1)]
        idx["i"] += 1
        return t

    mon = ApiCreditMonitor(
        notifier=notifier,
        config=AppConfig(api_credit=ApiCreditConfig(warn_usd=1.0, cooldown_hours=6)),
        env=env,
        clock=_clock,
        cooldown=timedelta(hours=6),
    )
    a = mon.check_and_maybe_alert()
    assert a.alerted is True
    assert len(notifier.messages) == 1
    assert "API_CREDIT_LOW" in notifier.messages[0]
    assert "openai" in notifier.messages[0]

    b = mon.check_and_maybe_alert()
    assert b.alerted is False
    assert len(notifier.messages) == 1

    c = mon.check_and_maybe_alert()
    assert c.alerted is True
    assert len(notifier.messages) == 2


def test_openai_api_credit_grants_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-not-real")
    env = EnvSettings(openai_api_key="sk-test-key-not-real")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "sk-test-key-not-real" not in str(request.url)
        if "credit_grants" in str(request.url):
            return httpx.Response(200, json={"total_available": 0.25})
        return httpx.Response(404, json={"error": "missing"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    notifier = _RecordingNotifier()
    mon = ApiCreditMonitor(
        notifier=notifier,
        env=env,
        config=AppConfig(api_credit=ApiCreditConfig(warn_usd=1.0)),
        http_client=client,
        clock=lambda: datetime(2026, 10, 23, 12, 0, tzinfo=UTC),
    )
    outcome = mon.check_and_maybe_alert()
    assert outcome.low
    assert outcome.low[0].remaining_usd == 0.25
    assert outcome.low[0].source == "api"
    assert outcome.alerted is True
    # Never leak key into Telegram text
    assert "sk-test" not in notifier.messages[0]


def test_deepseek_balance_parsed() -> None:
    env = EnvSettings(deepseek_api_key="ds-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/user/balance")
        return httpx.Response(
            200,
            json={
                "balance_infos": [
                    {"currency": "USD", "total_balance": "2.50"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mon = ApiCreditMonitor(
        notifier=NullTelegramNotifier(),
        env=env,
        config=AppConfig(api_credit=ApiCreditConfig(warn_usd=1.0)),
        http_client=client,
    )
    outcome = mon.check_and_maybe_alert()
    assert outcome.low == ()
    assert outcome.probed[0].provider == "deepseek"
    assert outcome.probed[0].remaining_usd == 2.5
    assert outcome.alerted is False


def test_unavailable_openai_api_falls_back_gracefully() -> None:
    env = EnvSettings(openai_api_key="sk-no-billing")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mon = ApiCreditMonitor(
        notifier=_RecordingNotifier(),
        env=env,
        http_client=client,
    )
    outcome = mon.check_and_maybe_alert()
    assert outcome.alerted is False
    assert outcome.probed[0].source == "unavailable"
    assert outcome.probed[0].remaining_usd is None


def test_above_threshold_no_alert() -> None:
    env = EnvSettings(openai_credit_usd=5.0, api_credit_warn_usd=1.0)
    notifier = _RecordingNotifier()
    mon = ApiCreditMonitor(notifier=notifier, env=env)
    outcome = mon.check_and_maybe_alert()
    assert outcome.alerted is False
    assert notifier.messages == []
