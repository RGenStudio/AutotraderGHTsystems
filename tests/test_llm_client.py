"""M5 LLMClient — mock backend, schema validation, timeout, cost hook."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from autotrader.journal import open_trade_journal
from autotrader.llm import LLMClient, MockLLMBackend, create_llm_client
from autotrader.llm.client import LLMResult
from autotrader.llm.factory import journal_cost_hook, make_recording_cost_hook
from autotrader.llm.types import ChatMessage, LLMUsage


class _TinySchema(BaseModel):
    direction: str
    confidence: int = Field(ge=0, le=100)


@pytest.fixture
def mock_backend() -> MockLLMBackend:
    return MockLLMBackend()


def test_create_llm_client_defaults_to_mock() -> None:
    client = create_llm_client(force_mock=True)
    assert isinstance(client, LLMClient)


def test_complete_validates_schema(mock_backend: MockLLMBackend) -> None:
    mock_backend.set_response(
        "mock-cheap", {"direction": "long", "confidence": 70}
    )
    client = LLMClient(mock_backend, timeout_s=5)
    result = client.complete(
        model="mock-cheap",
        messages=[ChatMessage(role="user", content="{}")],
        schema=_TinySchema,
        agent_name="technical_analyst",
    )
    assert result.success
    assert result.parsed is not None
    assert result.parsed.direction == "long"
    assert result.should_trade


def test_bad_json_does_not_trade(mock_backend: MockLLMBackend) -> None:
    mock_backend.enqueue("not-json{{{")
    client = LLMClient(mock_backend)
    result = client.complete(
        model="mock-cheap",
        messages=[{"role": "user", "content": "hi"}],
        schema=_TinySchema,
    )
    assert not result.success
    assert result.parsed is None
    assert not result.should_trade
    assert "bad_json" in result.error


def test_schema_invalid_does_not_trade(mock_backend: MockLLMBackend) -> None:
    mock_backend.enqueue({"direction": "long", "confidence": 999})
    client = LLMClient(mock_backend)
    result = client.complete(
        model="x",
        messages=[ChatMessage(role="user", content="{}")],
        schema=_TinySchema,
    )
    assert not result.success
    assert "schema_invalid" in result.error


def test_backend_exception_soft_fails(mock_backend: MockLLMBackend) -> None:
    mock_backend.fail_with = RuntimeError("boom")
    client = LLMClient(mock_backend)
    result = client.complete(
        model="x",
        messages=[ChatMessage(role="user", content="{}")],
        schema=_TinySchema,
    )
    assert not result.success
    assert "llm_error" in result.error


def test_timeout_error_soft_fails(mock_backend: MockLLMBackend) -> None:
    mock_backend.fail_with = TimeoutError("deadline")
    client = LLMClient(mock_backend, timeout_s=1)
    result = client.complete(
        model="x",
        messages=[ChatMessage(role="user", content="{}")],
        schema=_TinySchema,
    )
    assert not result.success
    assert "timeout" in result.error


def test_cost_hook_invoked_on_success(mock_backend: MockLLMBackend) -> None:
    sink: list[tuple[LLMUsage, str]] = []
    mock_backend.set_response("m", {"direction": "neutral", "confidence": 10})
    client = LLMClient(mock_backend, cost_hook=make_recording_cost_hook(sink))
    client.complete(
        model="m",
        messages=[ChatMessage(role="user", content="{}")],
        schema=_TinySchema,
        agent_name="technical_analyst",
    )
    assert len(sink) == 1
    assert sink[0][1] == "technical_analyst"
    assert sink[0][0].tokens_in > 0


def test_cost_hook_writes_journal_costs(tmp_path: Path, mock_backend: MockLLMBackend) -> None:
    journal = open_trade_journal(f"sqlite:///{tmp_path / 'costs.db'}")
    mock_backend.set_response("m", {"direction": "short", "confidence": 40})
    client = LLMClient(mock_backend, cost_hook=journal_cost_hook(journal))
    result = client.complete(
        model="m",
        messages=[ChatMessage(role="user", content="{}")],
        schema=_TinySchema,
        agent_name="news_analyst",
    )
    assert result.success
    # Hook returns cost row id
    assert result.agent_call_id is not None


def test_llm_result_type_guard() -> None:
    usage = LLMUsage(model="m")
    result: LLMResult[_TinySchema] = LLMResult(
        success=False, parsed=None, raw_text="", usage=usage, error="x"
    )
    assert not result.should_trade
