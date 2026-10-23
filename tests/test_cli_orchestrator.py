"""CLI: ``python -m autotrader`` smoke + ``run --once``."""

from __future__ import annotations

import autotrader.__main__ as cli
from autotrader.__main__ import main
from autotrader.orchestrator import cycle as orch_cycle


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


def test_run_once_respects_http_backend_flag(monkeypatch, capsys) -> None:
    """CLI must not hardcode force_mock_llm=True when LLM_BACKEND=http."""
    captured: dict[str, bool] = {}
    real_build = orch_cycle.build_orchestrator

    def _spy_build(**kwargs):
        captured["force_mock_llm"] = bool(kwargs.get("force_mock_llm"))
        # Keep CI offline: still inject mock LLM even when force_mock_llm is False.
        kwargs = dict(kwargs)
        kwargs["force_mock_llm"] = True
        return real_build(**kwargs)

    monkeypatch.setenv("LLM_BACKEND", "http")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "build_orchestrator", _spy_build)

    code = main(["run", "--once", "--at", "2026-10-14T15:00:00+00:00"])
    assert code == 0
    assert captured.get("force_mock_llm") is False
    out = capsys.readouterr().out
    assert "llm_backend=http" in out
