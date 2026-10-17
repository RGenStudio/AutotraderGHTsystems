"""Telegram Bot API notifier — soft-fail on network/API errors."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from autotrader.config import EnvSettings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


@runtime_checkable
class TelegramSender(Protocol):
    """Minimal send interface used by the orchestrator."""

    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        """Return True when the message was accepted; False on soft failure."""
        ...

    @property
    def enabled(self) -> bool:
        """True when credentials are configured and sends will be attempted."""
        ...


class NullTelegramNotifier:
    """No-op notifier when TELEGRAM_* is unset (default in CI)."""

    @property
    def enabled(self) -> bool:
        return False

    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        _ = text, parse_mode
        return False


class TelegramNotifier:
    """
    Send alerts via Telegram Bot API ``sendMessage``.

    Hard rules for M6:
    - Use ``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_CHAT_ID`` from env when set.
    - Never raise out of :meth:`send` — log and return False so the cycle continues.
    - Tests inject a mock ``http_client`` (or use :class:`NullTelegramNotifier`).
    """

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        timeout_s: float = 10.0,
        http_client: httpx.Client | None = None,
        api_base: str = TELEGRAM_API_BASE,
    ) -> None:
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("bot_token and chat_id are required")
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.timeout_s = timeout_s
        self._client = http_client
        self.api_base = api_base.rstrip("/")
        self._owns_client = http_client is None

    @property
    def enabled(self) -> bool:
        return True

    def _url(self) -> str:
        return f"{self.api_base}/bot{self.bot_token}/sendMessage"

    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            client = self._client
            if client is None:
                with httpx.Client(timeout=self.timeout_s) as owned:
                    response = owned.post(self._url(), json=payload)
                    response.raise_for_status()
                    data = response.json()
            else:
                response = client.post(self._url(), json=payload, timeout=self.timeout_s)
                response.raise_for_status()
                data = response.json()
            if isinstance(data, dict) and data.get("ok") is False:
                logger.warning("Telegram API returned ok=false: %s", data)
                return False
            return True
        except Exception as exc:  # noqa: BLE001 — soft-fail by design
            logger.warning("Telegram send failed (continuing cycle): %s", exc)
            return False

    def notify_approve(self, *, symbol: str, reason: str, detail: str = "") -> bool:
        return self.send(_format("APPROVE", symbol=symbol, reason=reason, detail=detail))

    def notify_reject(self, *, symbol: str, reason: str, detail: str = "") -> bool:
        return self.send(_format("REJECT", symbol=symbol, reason=reason, detail=detail))

    def notify_kill(self, *, reason: str, detail: str = "") -> bool:
        return self.send(_format("KILL", symbol="-", reason=reason, detail=detail))

    def notify_error(self, *, symbol: str, reason: str, detail: str = "") -> bool:
        return self.send(_format("ERROR", symbol=symbol, reason=reason, detail=detail))


def _format(kind: str, *, symbol: str, reason: str, detail: str) -> str:
    lines = [
        f"[AutoTrader] {kind}",
        f"symbol={symbol}",
        f"reason={reason}",
    ]
    if detail.strip():
        lines.append(detail.strip()[:500])
    return "\n".join(lines)


def create_telegram_notifier(
    *,
    env: EnvSettings | None = None,
    http_client: httpx.Client | None = None,
    force_null: bool = False,
) -> TelegramSender:
    """
    Build a notifier from env.

    Missing or empty ``TELEGRAM_*`` → :class:`NullTelegramNotifier` (CI default).
    """
    if force_null:
        return NullTelegramNotifier()
    settings = env or EnvSettings()
    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    if not token or not chat_id:
        logger.info("Telegram disabled (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID unset)")
        return NullTelegramNotifier()
    return TelegramNotifier(
        bot_token=token,
        chat_id=chat_id,
        http_client=http_client,
    )
