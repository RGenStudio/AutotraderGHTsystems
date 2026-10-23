"""
Best-effort LLM API credit / balance check → Telegram low-balance alert.

Never logs full API keys. Providers without a reliable remaining-balance API
are skipped gracefully; optional ``OPENAI_CREDIT_USD`` covers OpenAI manually.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from autotrader.config import ApiCreditConfig, AppConfig, EnvSettings, load_config
from autotrader.telegram.notifier import TelegramSender

logger = logging.getLogger(__name__)

# Redact long secret-looking tokens in log strings (Bearer / sk-…).
_SECRETISH = re.compile(
    r"(?i)(bearer\s+)\S+|(sk-[A-Za-z0-9_\-]{8,})|(api[_-]?key[=:]\s*)\S+"
)


def redact_secrets(text: str) -> str:
    """Best-effort redact of bearer tokens / sk- keys from log text."""
    out = _SECRETISH.sub(
        lambda m: (
            f"{m.group(1)}***"
            if m.group(1)
            else (
                "sk-***"
                if m.group(2)
                else f"{m.group(3)}***"
            )
        ),
        text,
    )
    return out


@dataclass(frozen=True, slots=True)
class CreditProbeResult:
    """One provider balance probe (or skip)."""

    provider: str
    remaining_usd: float | None
    source: str  # api | env_manual | unavailable | error
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CreditCheckOutcome:
    """Aggregate check used by the orchestrator heartbeat hook."""

    probed: tuple[CreditProbeResult, ...]
    low: tuple[CreditProbeResult, ...]
    alerted: bool
    warn_usd: float


class ApiCreditMonitor:
    """
    Periodic remaining-credit probe with Telegram cooldown.

    Soft-fails on network/API errors. Designed for ``run --loop`` / cycle heartbeat.
    """

    def __init__(
        self,
        *,
        notifier: TelegramSender,
        config: AppConfig | None = None,
        env: EnvSettings | None = None,
        warn_usd: float | None = None,
        cooldown: timedelta | None = None,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.notifier = notifier
        self.env = env or EnvSettings()
        self.config = config or load_config()
        credit_cfg = self.config.api_credit or ApiCreditConfig()
        env_warn = self.env.api_credit_warn_usd
        self.warn_usd = float(
            warn_usd
            if warn_usd is not None
            else (env_warn if env_warn is not None else credit_cfg.warn_usd)
        )
        hours = float(credit_cfg.cooldown_hours)
        self.cooldown = cooldown if cooldown is not None else timedelta(hours=hours)
        self._client = http_client
        self._owns_client = http_client is None
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_alert_at: datetime | None = None

    def check_and_maybe_alert(self, *, now: datetime | None = None) -> CreditCheckOutcome:
        """
        Probe balances; if any remaining USD is below ``warn_usd``, Telegram once
        per cooldown. Never raises; never logs full API keys.
        """
        instant = now or self._clock()
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        else:
            instant = instant.astimezone(UTC)

        probes = tuple(self.probe_all())
        low = tuple(
            p
            for p in probes
            if p.remaining_usd is not None and p.remaining_usd < self.warn_usd
        )
        alerted = False
        if low and self._cooldown_elapsed(instant):
            alerted = self._send_alert(low)
            if alerted:
                self._last_alert_at = instant
        return CreditCheckOutcome(
            probed=probes,
            low=low,
            alerted=alerted,
            warn_usd=self.warn_usd,
        )

    def probe_all(self) -> list[CreditProbeResult]:
        """Best-effort probes for configured providers (skip when no key)."""
        results: list[CreditProbeResult] = []
        if (self.env.openai_api_key or "").strip() or self.env.openai_credit_usd is not None:
            results.append(self._probe_openai())
        if (self.env.deepseek_api_key or "").strip():
            results.append(self._probe_deepseek())
        if (self.env.anthropic_api_key or "").strip():
            results.append(
                CreditProbeResult(
                    provider="anthropic",
                    remaining_usd=None,
                    source="unavailable",
                    detail="no simple remaining-balance API; skip",
                )
            )
        return results

    def _cooldown_elapsed(self, now: datetime) -> bool:
        if self._last_alert_at is None:
            return True
        return (now - self._last_alert_at) >= self.cooldown

    def _send_alert(self, low: tuple[CreditProbeResult, ...]) -> bool:
        lines = [
            "[AutoTrader] API_CREDIT_LOW",
            f"warn_usd={self.warn_usd}",
        ]
        for p in low:
            rem = f"{p.remaining_usd:.4f}" if p.remaining_usd is not None else "?"
            lines.append(f"{p.provider} remaining_usd={rem} source={p.source}")
        text = "\n".join(lines)
        try:
            ok = bool(self.notifier.send(text))
            if ok:
                logger.warning(
                    "API credit low alert sent (providers=%s warn_usd=%s)",
                    ",".join(p.provider for p in low),
                    self.warn_usd,
                )
            return ok
        except Exception as exc:  # noqa: BLE001 — soft-fail
            logger.warning(
                "API credit alert Telegram failed: %s",
                redact_secrets(str(exc)),
            )
            return False

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=15.0)

    def _probe_openai(self) -> CreditProbeResult:
        """
        Try known OpenAI billing/credit endpoints; fall back to OPENAI_CREDIT_USD.

        Standard API keys often cannot read remaining prepaid balance — that
        limitation is documented in the ops note. Manual env is the reliable path.
        """
        manual = self.env.openai_credit_usd
        if manual is not None:
            try:
                value = float(manual)
            except (TypeError, ValueError):
                value = None
            if value is not None:
                return CreditProbeResult(
                    provider="openai",
                    remaining_usd=value,
                    source="env_manual",
                    detail="OPENAI_CREDIT_USD",
                )

        api_key = (self.env.openai_api_key or "").strip()
        if not api_key:
            return CreditProbeResult(
                provider="openai",
                remaining_usd=None,
                source="unavailable",
                detail="no OPENAI_API_KEY / OPENAI_CREDIT_USD",
            )

        # Known (often restricted) dashboard-style endpoints — best-effort only.
        endpoints = (
            "https://api.openai.com/v1/dashboard/billing/credit_grants",
            "https://api.openai.com/dashboard/billing/credit_grants",
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        owns = self._client is None
        client = self._http()
        try:
            for url in endpoints:
                try:
                    response = client.get(url, headers=headers)
                    if response.status_code in {401, 403, 404}:
                        logger.info(
                            "OpenAI credit endpoint unavailable status=%s",
                            response.status_code,
                        )
                        continue
                    if response.status_code >= 400:
                        continue
                    data = response.json()
                    remaining = _parse_openai_credit_grants(data)
                    if remaining is not None:
                        return CreditProbeResult(
                            provider="openai",
                            remaining_usd=remaining,
                            source="api",
                            detail=url.rsplit("/", 1)[-1],
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.info(
                        "OpenAI credit probe skip: %s",
                        redact_secrets(str(exc)),
                    )
            return CreditProbeResult(
                provider="openai",
                remaining_usd=None,
                source="unavailable",
                detail=(
                    "no reliable remaining-balance API for this key; "
                    "set OPENAI_CREDIT_USD manually"
                ),
            )
        finally:
            if owns and self._client is None:
                client.close()

    def _probe_deepseek(self) -> CreditProbeResult:
        """DeepSeek exposes ``GET /user/balance`` (total_balance as string USD)."""
        api_key = (self.env.deepseek_api_key or "").strip()
        if not api_key:
            return CreditProbeResult(
                provider="deepseek",
                remaining_usd=None,
                source="unavailable",
                detail="no DEEPSEEK_API_KEY",
            )
        url = "https://api.deepseek.com/user/balance"
        headers = {"Authorization": f"Bearer {api_key}"}
        owns = self._client is None
        client = self._http()
        try:
            response = client.get(url, headers=headers)
            if response.status_code >= 400:
                return CreditProbeResult(
                    provider="deepseek",
                    remaining_usd=None,
                    source="error",
                    detail=f"status={response.status_code}",
                )
            data = response.json()
            remaining = _parse_deepseek_balance(data)
            if remaining is None:
                return CreditProbeResult(
                    provider="deepseek",
                    remaining_usd=None,
                    source="unavailable",
                    detail="balance payload missing total_balance",
                )
            return CreditProbeResult(
                provider="deepseek",
                remaining_usd=remaining,
                source="api",
                detail="user/balance",
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "DeepSeek credit probe skip: %s",
                redact_secrets(str(exc)),
            )
            return CreditProbeResult(
                provider="deepseek",
                remaining_usd=None,
                source="error",
                detail=redact_secrets(str(exc))[:200],
            )
        finally:
            if owns and self._client is None:
                client.close()


def _parse_openai_credit_grants(data: Any) -> float | None:
    """Parse legacy credit_grants JSON if present."""
    if not isinstance(data, dict):
        return None
    for key in ("total_available", "total_granted"):
        if key in data:
            try:
                return float(data[key])
            except (TypeError, ValueError):
                pass
    grants = data.get("grants") or data.get("data")
    if isinstance(grants, list):
        total = 0.0
        found = False
        for g in grants:
            if not isinstance(g, dict):
                continue
            for k in ("grant_amount", "remaining_amount", "amount"):
                if k in g:
                    try:
                        total += float(g[k])
                        found = True
                        break
                    except (TypeError, ValueError):
                        continue
        if found:
            return total
    return None


def _parse_deepseek_balance(data: Any) -> float | None:
    """DeepSeek balance: ``balance_infos[].total_balance`` (string)."""
    if not isinstance(data, dict):
        return None
    infos = data.get("balance_infos") or data.get("data")
    if isinstance(data.get("balance_infos"), list):
        infos = data["balance_infos"]
    if not isinstance(infos, list):
        # Some shapes nest under data
        if isinstance(data.get("data"), dict):
            infos = data["data"].get("balance_infos")
        if not isinstance(infos, list):
            return None
    total = 0.0
    found = False
    for info in infos:
        if not isinstance(info, dict):
            continue
        raw = info.get("total_balance")
        if raw is None:
            continue
        try:
            total += float(raw)
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def create_api_credit_monitor(
    *,
    notifier: TelegramSender,
    config: AppConfig | None = None,
    env: EnvSettings | None = None,
    http_client: httpx.Client | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ApiCreditMonitor:
    """Factory used by the orchestrator wiring."""
    return ApiCreditMonitor(
        notifier=notifier,
        config=config,
        env=env,
        http_client=http_client,
        clock=clock,
    )
