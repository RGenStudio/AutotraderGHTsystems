"""Pydantic JSON schemas for Agents 1–4 (invalid ⇒ no trade)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TechnicalAnalysisOutput(BaseModel):
    """
    Agent 1 — Technical Analyst.

    Structure vs signal only. Must not propose size or order actions.
    """

    direction: Literal["long", "short", "neutral"]
    confidence: int = Field(..., ge=0, le=100)
    structure_supports_signal: bool
    key_levels: list[float] = Field(default_factory=list)
    reasoning: str = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _reject_size_or_order_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        forbidden = {
            "risk_pct",
            "requested_risk_pct",
            "volume",
            "lot",
            "lots",
            "order",
            "action",
            "stop_loss",
            "take_profit",
            "position_size",
        }
        present = forbidden.intersection(data.keys())
        if present:
            raise ValueError(
                f"Technical Analyst must not propose size/order fields: {sorted(present)}"
            )
        return data


class NewsAnalysisOutput(BaseModel):
    """Agent 2 — News & calendar (sentiment deferred)."""

    bias: Literal["positive", "negative", "neutral"]
    impact_level: Literal["low", "medium", "high"]
    no_trade_news: bool
    reasoning: str = Field(..., min_length=1)
    blackout_events: list[str] = Field(default_factory=list)


class RiskManagerOutput(BaseModel):
    """
    Agent 3 — Risk Manager proposal only.

    Risk Engine (code) remains the authority; this cannot raise project ceilings.
    """

    should_trade: bool
    risk_pct: float = Field(..., gt=0)
    stop_loss: float
    take_profit: float | None = None
    reasoning: str = Field(..., min_length=1)

    @field_validator("risk_pct")
    @classmethod
    def _risk_pct_sane(cls, value: float) -> float:
        # Soft ceiling mirror of project default; Risk Engine still enforces hard cap.
        if value > 100:
            raise ValueError("risk_pct must be <= 100")
        return value


class DecisionMakerOutput(BaseModel):
    """
    Agent 4 — final JSON action.

    Aligns with brief §11 plus fields needed to build RiskEngine DecisionPayload.
    Invalid instances must never reach execution (pipeline treats as no trade).
    """

    action: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    side: str | None = None
    risk_pct: float | None = Field(default=None, gt=0)
    stop_loss: float | None = None
    take_profit: float | None = None
    entry_price: float | None = Field(default=None, gt=0)
    stop_distance_price: float | None = Field(default=None, gt=0)
    confidence: int = Field(..., ge=0, le=100)
    reasoning: str = Field(..., min_length=1)
    conflicts_noted: list[str] = Field(default_factory=list)
    idempotency_key: str = ""

    @field_validator("action")
    @classmethod
    def _normalize_action(cls, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {
            "enter_long": "enter_long",
            "enter_short": "enter_short",
            "long": "enter_long",
            "short": "enter_short",
            "enter": "enter",
            "buy": "enter_long",
            "sell": "enter_short",
            "skip": "skip",
            "hold": "skip",
            "no_trade": "skip",
            "do_nothing": "skip",
            "exit": "skip",  # exit management is out of M5 Risk Engine scope
        }
        if normalized not in aliases:
            raise ValueError(
                "action must be enter_long/enter_short/enter/skip "
                f"(or hold/exit/no_trade); got {value!r}"
            )
        return aliases[normalized]

    @field_validator("symbol")
    @classmethod
    def _symbol_upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("side")
    @classmethod
    def _side_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in {"long", "buy"}:
            return "long"
        if normalized in {"short", "sell"}:
            return "short"
        raise ValueError("side must be long/short")

    @model_validator(mode="after")
    def _derive_side_and_distances(self) -> DecisionMakerOutput:
        side = self.side
        if self.action == "enter_long":
            side = "long"
        elif self.action == "enter_short":
            side = "short"
        elif self.action == "enter" and side is None:
            raise ValueError("side required when action is enter")

        # Mutate in-place — model_copy from mode=after is unsupported under __init__.
        object.__setattr__(self, "side", side)

        entering = self.action in {"enter", "enter_long", "enter_short"}
        if entering:
            if self.risk_pct is None:
                raise ValueError("risk_pct required for enter actions")
            if self.entry_price is None:
                raise ValueError("entry_price required for enter actions")
            if self.stop_loss is None and self.stop_distance_price is None:
                raise ValueError("stop_loss or stop_distance_price required for enter")
            if self.stop_distance_price is None and self.stop_loss is not None:
                distance = abs(float(self.entry_price) - float(self.stop_loss))
                if distance <= 0:
                    raise ValueError("stop_distance_price must be > 0")
                object.__setattr__(self, "stop_distance_price", distance)
        return self

    @property
    def is_enter(self) -> bool:
        return self.action in {"enter", "enter_long", "enter_short"}

    @property
    def risk_action(self) -> str:
        """Map to RiskEngine DecisionPayload.action (enter | skip)."""
        return "enter" if self.is_enter else "skip"

    def to_risk_payload(self, *, idempotency_key: str | None = None) -> dict[str, Any]:
        """Build a dict suitable for RiskEngine.evaluate(..., raw_json=...)."""
        key = (idempotency_key or self.idempotency_key or "").strip()
        if self.is_enter:
            return {
                "action": "enter",
                "symbol": self.symbol,
                "side": self.side or "long",
                "requested_risk_pct": float(self.risk_pct or 0),
                "stop_distance_price": float(self.stop_distance_price or 0),
                "entry_price": float(self.entry_price or 0),
                "idempotency_key": key,
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
                "confidence": self.confidence,
                "reasoning": self.reasoning,
                "conflicts_noted": list(self.conflicts_noted),
            }
        return {
            "action": "skip",
            "symbol": self.symbol,
            "side": self.side or "long",
            "requested_risk_pct": float(self.risk_pct or 0.01),
            "stop_distance_price": float(self.stop_distance_price or 0.0001),
            "entry_price": float(self.entry_price or 1.0),
            "idempotency_key": key or "skip",
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "conflicts_noted": list(self.conflicts_noted),
        }
