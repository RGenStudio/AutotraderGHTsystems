"""M0 smoke / repo hygiene tests."""

from __future__ import annotations

from pathlib import Path

from autotrader.__main__ import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_prints_mode_paper(capsys, monkeypatch) -> None:
    monkeypatch.delenv("MODE", raising=False)
    assert main([]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "MODE=paper"
    assert any("execution=paper" in line for line in out)


def test_env_example_lists_required_keys_empty() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    required = [
        "MODE=",
        "MT5_LOGIN=",
        "MT5_PASSWORD=",
        "MT5_SERVER=",
        "MT5_PATH=",
        "TELEGRAM_BOT_TOKEN=",
        "TELEGRAM_CHAT_ID=",
        "OPENAI_API_KEY=",
        "ANTHROPIC_API_KEY=",
        "DEEPSEEK_API_KEY=",
        "LLM_BASE_URL=",
        "NEWS_CALENDAR_URL=",
        "DATABASE_URL=",
    ]
    for key in required:
        assert key in text
    # No filled secret-looking assignments in the example
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        _, _, value = line.partition("=")
        assert value.strip() == "", f"expected empty value in .env.example: {line}"


def test_gitignore_excludes_dotenv() -> None:
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi
    assert "!.env.example" in gi
