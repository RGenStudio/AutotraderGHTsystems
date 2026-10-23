"""§13 paper pass gate checker — pass/fail report only; never enables live MODE."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from autotrader.config import PaperGateThresholds
from autotrader.paper_ab.types import AbRunResult, ArmMetrics, ArmName


@dataclass(frozen=True, slots=True)
class GateCheckItem:
    name: str
    passed: bool
    detail: str
    applies_to: str = "all"


@dataclass(frozen=True, slots=True)
class GateCheckResult:
    """
    §13 evaluation for a paper A/B run.

    ``passed`` is True only when every applicable criterion passes.
    This result **does not** flip ``MODE`` to live — human approval is required.
    """

    passed: bool
    checks: tuple[GateCheckItem, ...]
    mode_remains: str = "paper"
    live_enabled: bool = False
    summary: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mode_remains": self.mode_remains,
            "live_enabled": self.live_enabled,
            "summary": self.summary,
            "checks": [asdict(c) for c in self.checks],
            "meta": dict(self.meta),
        }

    def summary_lines(self) -> list[str]:
        lines = [
            f"section13_pass={self.passed}",
            f"mode_remains={self.mode_remains}",
            f"live_enabled={self.live_enabled}",
        ]
        for c in self.checks:
            mark = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        if self.summary:
            lines.append(self.summary)
        return lines


def check_section13_gates(
    result: AbRunResult,
    *,
    thresholds: PaperGateThresholds | None = None,
) -> GateCheckResult:
    """
    Evaluate locked §13 paper criteria against harness metrics.

    Minimum sample: **80 closed trades OR ``min_weeks`` calendar weeks**
    (default 2 — weaker statistically than 12; Bartender accepted). Whichever
    comes first; both dimensions are documented. Numeric risk/quality thresholds
    are never weakened. Pass never enables ``MODE=live``.
    """
    th = thresholds or PaperGateThresholds()
    checks: list[GateCheckItem] = []

    # Prefer rules+AI arm for single-arm absolute gates when present; else rules_only.
    primary = result.arm(ArmName.RULES_PLUS_AI) or result.arm(ArmName.RULES_ONLY)
    if primary is None:
        return GateCheckResult(
            passed=False,
            checks=(
                GateCheckItem(
                    name="arms_present",
                    passed=False,
                    detail="no arm metrics in run result",
                ),
            ),
            summary="No arm metrics — cannot evaluate §13.",
        )

    # --- Sample size (80 trades OR min_weeks) ---
    sample_ok = (
        primary.trades >= th.min_closed_trades
        or primary.calendar_weeks >= th.min_weeks
    )
    checks.append(
        GateCheckItem(
            name="min_sample",
            passed=sample_ok,
            detail=(
                f"trades={primary.trades} (need>={th.min_closed_trades}) OR "
                f"weeks={primary.calendar_weeks:.2f} (need>={th.min_weeks}); "
                f"arm={primary.arm.value}"
            ),
            applies_to=primary.arm.value,
        )
    )

    # Absolute gates on primary (rules+AI when both, else the single arm)
    for arm_metrics in result.arms.values():
        checks.extend(_absolute_checks(arm_metrics, th))

    # A/B relative gates when both arms present
    rules = result.arm(ArmName.RULES_ONLY)
    ai = result.arm(ArmName.RULES_PLUS_AI)
    if rules is not None and ai is not None:
        checks.extend(_ab_relative_checks(rules, ai, th))

    passed = all(c.passed for c in checks)
    summary = (
        "§13 paper criteria PASSED — MODE stays paper until a human explicitly "
        "approves live. This checker never enables live trading."
        if passed
        else "§13 paper criteria FAILED — remain on MODE=paper; do not go live."
    )
    return GateCheckResult(
        passed=passed,
        checks=tuple(checks),
        mode_remains="paper",
        live_enabled=False,
        summary=summary,
        meta={
            "thresholds": th.model_dump(),
            "ab_mode": result.ab_mode,
            "cycles": result.cycles,
        },
    )


def _absolute_checks(m: ArmMetrics, th: PaperGateThresholds) -> list[GateCheckItem]:
    dd_pct = m.max_drawdown_pct * 100.0
    net_pct = m.net_return_pct * 100.0
    bad_pct = m.bad_json_rate * 100.0
    items = [
        GateCheckItem(
            name="max_drawdown",
            passed=dd_pct <= th.max_drawdown_pct,
            detail=f"max_DD={dd_pct:.2f}% (limit<={th.max_drawdown_pct}%)",
            applies_to=m.arm.value,
        ),
        GateCheckItem(
            name="net_return",
            passed=net_pct > th.min_net_return_pct,
            detail=f"net_return={net_pct:.2f}% (need>{th.min_net_return_pct}%)",
            applies_to=m.arm.value,
        ),
        GateCheckItem(
            name="expectancy",
            passed=m.expectancy_r > th.min_expectancy_r,
            detail=f"expectancy_R={m.expectancy_r:.4f} (need>{th.min_expectancy_r})",
            applies_to=m.arm.value,
        ),
        GateCheckItem(
            name="reward_risk",
            passed=m.reward_risk >= th.min_reward_risk,
            detail=f"avg_win/avg_loss_R={m.reward_risk:.3f} (need>={th.min_reward_risk})",
            applies_to=m.arm.value,
        ),
    ]
    # bad-JSON only meaningful for rules+AI (Agent 4 calls)
    if m.arm == ArmName.RULES_PLUS_AI or m.agent4_calls > 0:
        items.append(
            GateCheckItem(
                name="bad_json_rate",
                passed=bad_pct <= th.max_bad_json_rate_pct,
                detail=(
                    f"bad_JSON={bad_pct:.2f}% "
                    f"({m.bad_json_count}/{m.agent4_calls} Agent4 calls; "
                    f"limit<={th.max_bad_json_rate_pct}%)"
                ),
                applies_to=m.arm.value,
            )
        )
    return items


def _ab_relative_checks(
    rules: ArmMetrics,
    ai: ArmMetrics,
    th: PaperGateThresholds,
) -> list[GateCheckItem]:
    """
    rules+AI: DD no worse than rules-only + ``ab_dd_tolerance_pp``;
    expectancy ≥ rules-only.
    """
    rules_dd_pp = rules.max_drawdown_pct * 100.0
    ai_dd_pp = ai.max_drawdown_pct * 100.0
    dd_limit = rules_dd_pp + th.ab_dd_tolerance_pp
    dd_ok = ai_dd_pp <= dd_limit
    exp_ok = ai.expectancy_r >= rules.expectancy_r
    return [
        GateCheckItem(
            name="ab_drawdown",
            passed=dd_ok,
            detail=(
                f"rules+AI DD={ai_dd_pp:.2f}pp vs rules-only={rules_dd_pp:.2f}pp "
                f"(limit <= rules-only + {th.ab_dd_tolerance_pp}pp = {dd_limit:.2f}pp)"
            ),
            applies_to="ab",
        ),
        GateCheckItem(
            name="ab_expectancy",
            passed=exp_ok,
            detail=(
                f"rules+AI expectancy_R={ai.expectancy_r:.4f} vs "
                f"rules-only={rules.expectancy_r:.4f} (need >= rules-only)"
            ),
            applies_to="ab",
        ),
    ]
