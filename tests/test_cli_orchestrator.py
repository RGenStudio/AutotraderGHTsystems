"""CLI: ``python -m autotrader`` smoke + ``run --once`` / ``--loop``."""

from __future__ import annotations

import pytest

import autotrader.__main__ as cli
from autotrader.__main__ import build_parser, main
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


def test_loop_flag_clears_once_path() -> None:
    """`--loop` must not leave a default `--once` that forces the single-cycle path."""
    args = build_parser().parse_args(["run", "--loop"])
    assert args.loop is True
    assert args.once is False
    assert args.max_cycles is None


def test_run_loop_schedules_multiple_cycles(monkeypatch, capsys) -> None:
    """`--loop --max-cycles N` must run N cycles (mock sleep; no real 1h wait)."""
    sleeps: list[float] = []

    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleeps.append(float(seconds)))

    code = main(["run", "--loop", "--max-cycles", "3"])
    assert code == 0
    out = capsys.readouterr().out
    assert "scheduler cycles=3" in out
    assert "cycle status=" not in out  # once-path summary must not appear
    # Sleep between cycles only (not after the final cycle).
    assert len(sleeps) == 2
    assert all(s == pytest.approx(3600.0) for s in sleeps)


def test_run_loop_keyboard_interrupt_stops_cleanly(monkeypatch, capsys) -> None:
    """Ctrl+C during sleep must mark scheduler_stop and return completed cycles."""
    calls = {"n": 0}

    def _sleep(_seconds: float) -> None:
        calls["n"] += 1
        if calls["n"] >= 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", _sleep)
    code = main(["run", "--loop"])
    assert code == 0
    out = capsys.readouterr().out
    assert "scheduler cycles=1" in out
