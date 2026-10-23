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
    assert cfg.llm.backend == "http"
    assert cfg.llm.timeout_seconds == 30
    assert cfg.llm.models.technical == "deepseek-chat"
    assert cfg.llm.models.news == "deepseek-chat"
    assert cfg.llm.models.risk_manager == "gpt-4o-mini"
    assert cfg.llm.models.decision_maker == "claude-sonnet-4-5"
    assert cfg.news.blackout_minutes == 30
    assert "USD" in cfg.news.high_impact_currencies
    assert cfg.api_credit.warn_usd == 1.0
    assert cfg.api_credit.cooldown_hours == 6.0


def test_paper_ab_defaults_from_yaml() -> None:
    from autotrader.config import AbMode

    cfg = load_yaml_config()
    assert cfg.paper_ab.ab_mode == AbMode.BOTH
    assert cfg.paper_ab.cycles == 50
    assert cfg.paper_ab.gates.min_closed_trades == 80
    assert cfg.paper_ab.gates.min_weeks == 2
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
    """``LLM_BACKEND=`` is unset so YAML default (http) applies."""
    monkeypatch.setenv("LLM_BACKEND", blank)
    from autotrader.config import EnvSettings
    from autotrader.llm.factory import resolve_llm_backend_name

    settings = EnvSettings()
    assert settings.llm_backend is None
    assert resolve_llm_backend_name(env=settings) == "http"


def test_env_mode_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODE", "backtest")
    cfg = load_config()
    assert cfg.mode == Mode.BACKTEST


def test_missing_yaml_falls_back_to_paper_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    cfg = load_yaml_config(missing)
    assert cfg.mode == Mode.PAPER
    assert cfg.risk.max_open_positions == 2


def _isolate_dotenv_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, with_dotenv: bool
) -> None:
    """Point REPO_ROOT + cwd at tmp so real workspace .env cannot interfere."""
    import autotrader.config as config_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_mod, "REPO_ROOT", tmp_path)
    (tmp_path / ".env.example").write_text("MT5_LOGIN=\n", encoding="utf-8")
    if with_dotenv:
        (tmp_path / ".env").write_text("MT5_LOGIN=\n", encoding="utf-8")


def test_warn_missing_dotenv_when_example_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """No .env + .env.example present + no keys → clear copy hint."""
    from autotrader.config import EnvSettings, maybe_warn_missing_dotenv

    for key in (
        "MT5_LOGIN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    _isolate_dotenv_paths(tmp_path, monkeypatch, with_dotenv=False)

    with caplog.at_level("WARNING", logger="autotrader.config"):
        warned = maybe_warn_missing_dotenv(env=EnvSettings(_env_file=None))
    assert warned is True
    assert "No .env file found" in caplog.text
    assert "copy .env.example .env" in caplog.text


def test_no_warn_when_dotenv_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from autotrader.config import EnvSettings, maybe_warn_missing_dotenv

    _isolate_dotenv_paths(tmp_path, monkeypatch, with_dotenv=True)

    with caplog.at_level("WARNING", logger="autotrader.config"):
        warned = maybe_warn_missing_dotenv(env=EnvSettings(_env_file=None))
    assert warned is False
    assert "No .env file found" not in caplog.text


def test_no_warn_when_llm_key_in_process_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from autotrader.config import EnvSettings, maybe_warn_missing_dotenv

    _isolate_dotenv_paths(tmp_path, monkeypatch, with_dotenv=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level("WARNING", logger="autotrader.config"):
        warned = maybe_warn_missing_dotenv(env=EnvSettings(_env_file=None))
    assert warned is False
    assert "No .env file found" not in caplog.text
