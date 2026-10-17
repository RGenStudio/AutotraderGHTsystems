"""Telegram notifier — mock HTTP; soft-fail never raises."""

from __future__ import annotations

import httpx
import pytest

from autotrader.config import EnvSettings
from autotrader.telegram import (
    NullTelegramNotifier,
    TelegramNotifier,
    create_telegram_notifier,
)


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, *, status_code: int = 200, body: dict | None = None, raise_exc=None):
        self.status_code = status_code
        self.body = body if body is not None else {"ok": True, "result": {}}
        self.raise_exc = raise_exc
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        return httpx.Response(self.status_code, json=self.body, request=request)


def test_null_notifier_disabled() -> None:
    n = NullTelegramNotifier()
    assert n.enabled is False
    assert n.send("hi") is False


def test_create_null_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    n = create_telegram_notifier(env=EnvSettings(), force_null=False)
    assert isinstance(n, NullTelegramNotifier)


def test_send_success_with_mock_http() -> None:
    transport = _FakeTransport()
    client = httpx.Client(transport=transport)
    n = TelegramNotifier(
        bot_token="tok",
        chat_id="123",
        http_client=client,
        api_base="https://api.telegram.test",
    )
    assert n.enabled is True
    assert n.notify_approve(symbol="EURUSD", reason="ok") is True
    assert len(transport.requests) == 1
    req = transport.requests[0]
    assert "sendMessage" in str(req.url)
    assert "tok" in str(req.url)


def test_send_soft_fails_on_http_error() -> None:
    transport = _FakeTransport(raise_exc=httpx.ConnectError("down"))
    client = httpx.Client(transport=transport)
    n = TelegramNotifier(bot_token="tok", chat_id="123", http_client=client)
    # Must not raise
    assert n.notify_reject(symbol="EURUSD", reason="max_open") is False
    assert n.notify_kill(reason="kill_switch_active") is False
    assert n.notify_error(symbol="USDJPY", reason="boom") is False


def test_send_soft_fails_on_api_ok_false() -> None:
    transport = _FakeTransport(body={"ok": False, "description": "Forbidden"})
    client = httpx.Client(transport=transport)
    n = TelegramNotifier(bot_token="tok", chat_id="123", http_client=client)
    assert n.send("hello") is False


def test_create_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    n = create_telegram_notifier(env=EnvSettings())
    assert isinstance(n, TelegramNotifier)
    assert n.bot_token == "env-tok"
    assert n.chat_id == "999"
