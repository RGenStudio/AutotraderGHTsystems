"""Shared agent helpers — LLM call + journal agent_calls recording."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from autotrader.journal.api import TradeJournal
from autotrader.llm.client import LLMClient, LLMResult
from autotrader.llm.types import ChatMessage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

PROMPT_VERSION = "m5-v1"


@dataclass(frozen=True, slots=True)
class AgentCallOutcome(Generic[T]):
    """One agent turn: validated output or soft failure (do not trade)."""

    agent_name: str
    result: LLMResult[T]
    agent_call_id: int | None = None

    @property
    def ok(self) -> bool:
        return self.result.should_trade

    @property
    def parsed(self) -> T | None:
        return self.result.parsed

    @property
    def error(self) -> str:
        return self.result.error


def run_structured_agent(
    *,
    client: LLMClient,
    journal: TradeJournal | None,
    agent_name: str,
    model: str,
    schema: type[T],
    system_prompt: str,
    user_payload: dict[str, Any],
    prompt_version: str = PROMPT_VERSION,
    decision_id: int | None = None,
) -> AgentCallOutcome[T]:
    """
    Call LLMClient with a JSON schema, journal the call, return outcome.

    Failures (timeout / bad JSON / schema) are soft: ``ok`` is False and the
    pipeline must not trade.
    """
    messages = [
        ChatMessage(
            role="user",
            content=json.dumps(user_payload, default=str, ensure_ascii=False),
        )
    ]
    llm_result = client.complete(
        model=model,
        messages=messages,
        schema=schema,
        agent_name=agent_name,
        system=system_prompt,
    )

    agent_call_id: int | None = None
    if journal is not None:
        try:
            agent_call_id = journal.record_agent_call(
                agent_name=agent_name,
                prompt_version=prompt_version,
                model=model,
                input_payload={"system": system_prompt, "user": user_payload},
                output_payload=_output_payload(llm_result),
                tokens_in=llm_result.usage.tokens_in,
                tokens_out=llm_result.usage.tokens_out,
                cost_usd=llm_result.usage.cost_usd,
                latency_ms=llm_result.usage.latency_ms or None,
                success=llm_result.success,
                error_message=llm_result.error,
                decision_id=decision_id,
            )
            # Link cost row when hook already wrote one without agent_call_id,
            # or write a cost line tied to this call.
            if llm_result.usage.cost_usd > 0 or llm_result.usage.tokens_in > 0:
                journal.record_cost(
                    kind="llm_api",
                    amount=float(llm_result.usage.cost_usd),
                    currency="USD",
                    agent_call_id=agent_call_id,
                    meta={
                        "agent_name": agent_name,
                        "model": model,
                        "tokens_in": llm_result.usage.tokens_in,
                        "tokens_out": llm_result.usage.tokens_out,
                    },
                )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to journal agent_call for %s", agent_name)

    return AgentCallOutcome(
        agent_name=agent_name,
        result=llm_result,
        agent_call_id=agent_call_id,
    )


def _output_payload(result: LLMResult[Any]) -> dict[str, Any] | None:
    if result.parsed is not None:
        return result.parsed.model_dump(mode="json")
    if result.raw_text:
        return {"raw_text": result.raw_text, "error": result.error}
    if result.error:
        return {"error": result.error}
    return None
