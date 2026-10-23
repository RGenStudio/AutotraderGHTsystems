"""Shared pytest fixtures — keep accidental MODE=live from poisoning the suite."""

from __future__ import annotations

import os

import pytest

from autotrader.config import Mode


@pytest.fixture(autouse=True)
def _default_mode_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Autouse: if a test does not set MODE, force paper.

    Tests that intentionally probe live must set MODE themselves and assert
    refusal — they cannot leave live enabled for sibling tests.
    """
    if "MODE" not in os.environ:
        monkeypatch.setenv("MODE", Mode.PAPER.value)
    # YAML default llm.backend is http; keep the suite on mock unless a test opts in.
    if "LLM_BACKEND" not in os.environ:
        monkeypatch.setenv("LLM_BACKEND", "mock")
