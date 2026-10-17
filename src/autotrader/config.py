"""Load non-secret YAML config and environment-backed settings."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


class Mode(StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


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
    timezone: str = "UTC"
    weekdays_only: bool = True
    start: str = "12:00"
    end: str = "21:00"


class AppConfig(BaseModel):
    mode: Mode = Mode.PAPER
    symbols: list[str] = Field(default_factory=lambda: ["EURUSD", "USDJPY"])
    timeframes: dict[str, str] = Field(
        default_factory=lambda: {"entry": "H1", "trend": "H4"}
    )
    active_window: ActiveWindow = Field(default_factory=ActiveWindow)
    risk: RiskLimits = Field(default_factory=RiskLimits)
    news: dict[str, Any] = Field(default_factory=lambda: {"blackout_minutes": 30})
    logging: dict[str, Any] = Field(
        default_factory=lambda: {"level": "INFO", "utc": True}
    )


class EnvSettings(BaseSettings):
    """Secrets and overrides from process env / local `.env` (never commit filled values)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: Mode | None = None
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
