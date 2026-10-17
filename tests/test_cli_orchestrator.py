"""CLI: ``python -m autotrader`` smoke + ``run --once``."""

from __future__ import annotations

from autotrader.__main__ import main


def test_bare_module_smoke(capsys) -> None:
    code = main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "MODE=paper" in out
    assert "llm_backend=" in out
    assert "telegram=" in out


def test_run_once(capsys) -> None:
    code = main(["run", "--once", "--at", "2026-10-14T15:00:00+00:00"])
    assert code == 0
    out = capsys.readouterr().out
    assert "MODE=paper" in out
    assert "cycle status=" in out
