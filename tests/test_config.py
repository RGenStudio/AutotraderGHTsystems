"""M0 config / MODE tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from autotrader.config import (
    DEFAULT_CONFIG_PATH,
    Mode,
    load_config,
    load_yaml_config,
    resolve_mode,
)


def test_default_config_yaml_exists() -> None:
    assert DEFAULT_CONFIG_PATH.is_file()


def test_yaml_defaults_are_paper_and_locked_symbols() -> None:
    cfg = load_yaml_config()
    assert cfg.mode == Mode.PAPER
    assert cfg.symbols == ["EURUSD", "USDJPY"]
    assert cfg.symbol_map == {}
    assert cfg.timeframes["entry"] == "H1"
    assert cfg.timeframes["trend"] == "H4"


def test_symbol_map_loads_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text(
        "mode: paper\n"
        "symbols: [EURUSD, USDJPY]\n"
        "symbol_map:\n"
        "  EURUSD: EURUSDm\n"
        "  USDJPY: USDJPYm\n",
        encoding="utf-8",
    )
    cfg = load_yaml_config(path)
    assert cfg.symbol_map == {"EURUSD": "EURUSDm", "USDJPY": "USDJPYm"}


def test_risk_defaults_from_yaml() -> None:
    cfg = load_yaml_config()
    assert cfg.risk.max_risk_per_trade_pct == 0.5
    assert cfg.risk.max_daily_loss_pct == 2.0
    assert cfg.risk.max_weekly_drawdown_pct == 5.0
    assert cfg.risk.max_open_positions == 2


def test_llm_and_news_defaults_from_yaml() -> None:
    cfg = load_yaml_config()
    assert cfg.llm.backend == "mock"
    assert cfg.llm.timeout_seconds == 30
    assert cfg.llm.models.technical == "mock-cheap"
    assert cfg.llm.models.decision_maker == "mock-strong"
    assert cfg.news.blackout_minutes == 30
    assert "USD" in cfg.news.high_impact_currencies


def test_paper_ab_defaults_from_yaml() -> None:
    from autotrader.config import AbMode

    cfg = load_yaml_config()
    assert cfg.paper_ab.ab_mode == AbMode.BOTH
    assert cfg.paper_ab.cycles == 50
    assert cfg.paper_ab.gates.min_closed_trades == 80
    assert cfg.paper_ab.gates.max_drawdown_pct == 8.0
    assert cfg.paper_ab.gates.max_bad_json_rate_pct == 3.0


def test_resolve_mode_defaults_to_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODE", raising=False)
    assert resolve_mode() == Mode.PAPER


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_empty_mode_env_defaults_to_paper(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """``MODE=`` in .env must not ValidationError — treat as unset → paper."""
    monkeypatch.setenv("MODE", blank)
    from autotrader.config import EnvSettings

    settings = EnvSettings()
    assert settings.mode is None
    assert resolve_mode(env=settings) == Mode.PAPER
    assert load_config().mode == Mode.PAPER


@pytest.mark.parametrize("blank", ["", "  "])
def test_empty_llm_backend_env_is_unset(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """``LLM_BACKEND=`` is unset so YAML/default mock applies."""
    monkeypatch.setenv("LLM_BACKEND", blank)
    from autotrader.config import EnvSettings
    from autotrader.llm.factory import resolve_llm_backend_name

    settings = EnvSettings()
    assert settings.llm_backend is None
    assert resolve_llm_backend_name(env=settings) == "mock"


def test_env_mode_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODE", "backtest")
    cfg = load_config()
    assert cfg.mode == Mode.BACKTEST


def test_missing_yaml_falls_back_to_paper_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    cfg = load_yaml_config(missing)
    assert cfg.mode == Mode.PAPER
    assert cfg.risk.max_open_positions == 2
