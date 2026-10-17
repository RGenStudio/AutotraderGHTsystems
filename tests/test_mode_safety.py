"""MODE=paper default — live must be impossible to enable accidentally."""

from __future__ import annotations

import pytest

from autotrader.__main__ import main
from autotrader.config import Mode, load_config, require_non_live_mode
from autotrader.execution.factory import LiveModeForbiddenError, refuse_live_mode


def test_default_mode_is_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODE", raising=False)
    cfg = load_config()
    assert cfg.mode == Mode.PAPER


def test_require_non_live_allows_paper_and_backtest() -> None:
    assert require_non_live_mode(Mode.PAPER) == Mode.PAPER
    assert require_non_live_mode(Mode.BACKTEST) == Mode.BACKTEST


def test_require_non_live_refuses_live() -> None:
    with pytest.raises(LiveModeForbiddenError):
        require_non_live_mode(Mode.LIVE)
    with pytest.raises(LiveModeForbiddenError):
        refuse_live_mode(Mode.LIVE)


def test_cli_exits_nonzero_on_live(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("MODE", "live")
    code = main([])
    assert code == 2
    err = capsys.readouterr().err
    assert "forbidden" in err.lower() or "live" in err.lower()


def test_cli_paper_mentions_paper_execution(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("MODE", "paper")
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "MODE=paper" in out
    assert "execution=paper" in out
