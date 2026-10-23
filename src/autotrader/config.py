"""Load non-secret YAML config and environment-backed settings."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _blank_str_to_none(value: Any) -> Any:
    """Treat empty / whitespace-only env strings as unset (None)."""
    if isinstance(value, str) and not value.strip():
        return None
    return value

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


class Mode(StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class AbMode(StrEnum):
    """Paper A/B harness arm selection (M8)."""

    RULES_ONLY = "rules_only"
    RULES_PLUS_AI = "rules_plus_ai"
    BOTH = "both"


class PaperGateThresholds(BaseModel):
    """
    Locked §13 paper pass criteria (project defaults).

    Sample size uses OR logic: ``min_closed_trades`` **or** ``min_weeks``
    (whichever comes first). ``min_weeks=2`` is weaker statistically than the
    prior 12-week default — Bartender LV.1 accepted that trade-off.

    The gate checker evaluates these and **never** enables ``MODE=live``.
    """

    min_closed_trades: int = Field(default=80, ge=1)
    min_weeks: int = Field(default=2, ge=1)
    max_drawdown_pct: float = Field(default=8.0, gt=0)  # percent points
    min_net_return_pct: float = Field(default=0.0)  # must be strictly >
    min_expectancy_r: float = Field(default=0.0)  # must be strictly >
    min_reward_risk: float = Field(default=1.0, ge=0)
    max_bad_json_rate_pct: float = Field(default=3.0, ge=0)  # percent of Agent 4 calls
    ab_dd_tolerance_pp: float = Field(default=1.0, ge=0)  # rules+AI vs rules-only

    @model_validator(mode="before")
    @classmethod
    def _alias_legacy_max_calendar_weeks(cls, data: Any) -> Any:
        """Accept legacy YAML key ``max_calendar_weeks`` as ``min_weeks``."""
        if not isinstance(data, dict):
            return data
        if "min_weeks" not in data and "max_calendar_weeks" in data:
            data = dict(data)
            data["min_weeks"] = data.pop("max_calendar_weeks")
        elif "max_calendar_weeks" in data:
            data = dict(data)
            data.pop("max_calendar_weeks", None)
        return data


class PaperAbConfig(BaseModel):
    """Synthetic/mock paper A/B harness settings (not a multi-week live run)."""

    ab_mode: AbMode = AbMode.BOTH
    cycles: int = Field(default=50, ge=1)
    seed: int = 42
    starting_equity: float = Field(default=10_000.0, gt=0)
    signal_rate: float = Field(default=0.55, ge=0, le=1)
    bad_json_rate: float = Field(default=0.02, ge=0, le=1)
    ai_skip_rate: float = Field(default=0.15, ge=0, le=1)
    positive_bias: float = Field(default=0.55, ge=0, le=1)
    gates: PaperGateThresholds = Field(default_factory=PaperGateThresholds)


class RiskLimits(BaseModel):
    """Hard risk ceilings enforced by code (AI cannot raise these)."""

    max_risk_per_trade_pct: float = Field(default=0.5, gt=0)
    max_daily_loss_pct: float = Field(default=2.0, gt=0)
    max_weekly_drawdown_pct: float = Field(default=5.0, gt=0)
    max_open_positions: int = Field(default=2, ge=1)

    @field_validator(
        "max_risk_per_trade_pct",
        "max_daily_loss_pct",
        "max_weekly_drawdown_pct",
    )
    @classmethod
    def _pct_in_sane_range(cls, value: float) -> float:
        if value > 100:
            raise ValueError("percentage values must be <= 100")
        return value


class ActiveWindow(BaseModel):
    """
    UTC entry window. Default is effectively 24h (00:00–24:00, all days).

    ``end: "24:00"`` is an exclusive end-of-day sentinel. Kill switch / risk
    rules are independent of this window.
    """

    timezone: str = "UTC"
    weekdays_only: bool = False
    start: str = "00:00"
    end: str = "24:00"


class LLMModels(BaseModel):
    """
    Model slots by role (real capability defaults).

    Agents 1–2 stay on a cheaper-capable model; Agents 3–4 use gpt-4o.
    Override all four to ``gpt-4o`` in YAML if preferred.
    """

    technical: str = "gpt-4o-mini"
    news: str = "gpt-4o-mini"
    risk_manager: str = "gpt-4o"
    decision_maker: str = "gpt-4o"


class LLMConfig(BaseModel):
    """Non-secret LLM client settings (keys stay in `.env`)."""

    backend: str = "http"  # mock | http (no keys → soft-fallback to mock)
    timeout_seconds: float = Field(default=30.0, gt=0)
    models: LLMModels = Field(default_factory=LLMModels)


class ApiCreditConfig(BaseModel):
    """Best-effort remaining-credit alert → Telegram (never logs API keys)."""

    warn_usd: float = Field(default=1.0, gt=0)
    cooldown_hours: float = Field(default=6.0, gt=0)


class NewsConfig(BaseModel):
    blackout_minutes: int = Field(default=30, ge=0)
    high_impact_currencies: list[str] = Field(
        default_factory=lambda: ["USD", "EUR", "JPY"]
    )


class AppConfig(BaseModel):
    mode: Mode = Mode.PAPER
    # App-facing pair names. May be broker-native (e.g. Exness EURUSDm — exact
    # casing) or logical (EURUSD) with optional symbol_map → Market Watch wire name.
    symbols: list[str] = Field(default_factory=lambda: ["EURUSD", "USDJPY"])
    # Optional logical → broker wire name (Exness often uses EURUSDm / USDJPYm).
    # Values keep broker casing (never uppercased); keys match case-insensitively.
    symbol_map: dict[str, str] = Field(default_factory=dict)
    timeframes: dict[str, str] = Field(
        default_factory=lambda: {"entry": "H1", "trend": "H4"}
    )
    active_window: ActiveWindow = Field(default_factory=ActiveWindow)
    risk: RiskLimits = Field(default_factory=RiskLimits)
    news: NewsConfig = Field(default_factory=NewsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    api_credit: ApiCreditConfig = Field(default_factory=ApiCreditConfig)
    paper_ab: PaperAbConfig = Field(default_factory=PaperAbConfig)
    logging: dict[str, Any] = Field(
        default_factory=lambda: {"level": "INFO", "utc": True}
    )
    database: dict[str, Any] = Field(default_factory=lambda: {"url": ""})
    backtest: dict[str, Any] = Field(default_factory=dict)


class EnvSettings(BaseSettings):
    """Secrets and overrides from process env / local `.env` (never commit filled values)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: Mode | None = None
    # Optional override for llm.backend (mock|http). Blank → unset → YAML/default.
    llm_backend: str | None = None
    mt5_login: str | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_path: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None
    llm_base_url: str | None = None
    news_calendar_url: str | None = None
    database_url: str | None = None
    # Credit low-alert (Telegram). Blank → unset → YAML api_credit.warn_usd / 1.0.
    api_credit_warn_usd: float | None = None
    # Optional manual OpenAI remaining balance when no reliable billing API.
    openai_credit_usd: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _empty_env_strings_as_unset(cls, data: Any) -> Any:
        """
        ``MODE=`` / ``LLM_BACKEND=`` in ``.env.example`` must not ValidationError.

        Empty or whitespace-only values are treated as unset so defaults apply
        (``MODE`` → paper via YAML; ``LLM_BACKEND`` → YAML ``llm.backend`` / http).
        """
        if not isinstance(data, dict):
            return data
        return {key: _blank_str_to_none(value) for key, value in data.items()}


def load_yaml_config(path: Path | None = None) -> AppConfig:
    config_path = path or Path(os.environ.get("AUTOTRADER_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        return AppConfig()
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw)


def resolve_mode(config: AppConfig | None = None, env: EnvSettings | None = None) -> Mode:
    """Environment MODE wins when set; otherwise YAML; default paper."""
    settings = env or EnvSettings()
    if settings.mode is not None:
        return settings.mode
    app = config or load_yaml_config()
    return app.mode


def load_config(path: Path | None = None) -> AppConfig:
    """Load YAML then apply env MODE override (default remains paper)."""
    app = load_yaml_config(path)
    mode = resolve_mode(app)
    return app.model_copy(update={"mode": mode})


def require_non_live_mode(mode: Mode) -> Mode:
    """
    Refuse ``live`` for this project phase.

    Import is deferred so ``config`` stays free of execution-layer cycles.
    """
    from autotrader.execution.factory import refuse_live_mode

    refuse_live_mode(mode)
    return mode
