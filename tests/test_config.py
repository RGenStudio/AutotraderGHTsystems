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
    assert cfg.timeframes["entry"] == "H1"
    assert cfg.timeframes["trend"] == "H4"


def test_risk_defaults_from_yaml() -> None:
    cfg = load_yaml_config()
    assert cfg.risk.max_risk_per_trade_pct == 0.5
    assert cfg.risk.max_daily_loss_pct == 2.0
    assert cfg.risk.max_weekly_drawdown_pct == 5.0
    assert cfg.risk.max_open_positions == 2


def test_resolve_mode_defaults_to_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODE", raising=False)
    assert resolve_mode() == Mode.PAPER


def test_env_mode_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODE", "backtest")
    cfg = load_config()
    assert cfg.mode == Mode.BACKTEST


def test_missing_yaml_falls_back_to_paper_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    cfg = load_yaml_config(missing)
    assert cfg.mode == Mode.PAPER
    assert cfg.risk.max_open_positions == 2
