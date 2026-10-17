"""Write paper A/B reports (markdown + JSON) under ``reports/``."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autotrader.config import REPO_ROOT
from autotrader.paper_ab.gates import GateCheckResult
from autotrader.paper_ab.types import AbRunResult, ClosedPaperTrade

DEFAULT_REPORTS_DIR = REPO_ROOT / "reports"


def write_ab_report(
    result: AbRunResult,
    gate: GateCheckResult,
    *,
    output_dir: Path | None = None,
    basename: str | None = None,
) -> dict[str, Path]:
    """
    Persist markdown + JSON report files.

    Runtime reports under ``reports/`` are gitignored; commit only
    ``reports/examples/`` samples.
    """
    out = output_dir or DEFAULT_REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    stamp = basename or datetime.now(UTC).strftime("paper-ab-%Y%m%dT%H%M%SZ")
    json_path = out / f"{stamp}.json"
    md_path = out / f"{stamp}.md"

    payload = build_report_dict(result, gate)
    json_path.write_text(
        json.dumps(payload, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(result, gate), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def build_report_dict(result: AbRunResult, gate: GateCheckResult) -> dict[str, Any]:
    trades_out: dict[str, list[dict[str, Any]]] = {}
    for arm, trades in result.trades_by_arm.items():
        trades_out[arm] = [_trade_dict(t) for t in trades]
    return {
        "kind": "paper_ab_report",
        "ab_mode": result.ab_mode,
        "cycles": result.cycles,
        "seed": result.seed,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "arms": {k: v.to_dict() for k, v in result.arms.items()},
        "gates": gate.to_dict(),
        "trades_by_arm": trades_out,
        "meta": dict(result.meta),
        "disclaimer": (
            "Synthetic/mock paper A/B harness — not a multi-week live paper run. "
            "Gate pass does not enable MODE=live."
        ),
    }


def render_markdown(result: AbRunResult, gate: GateCheckResult) -> str:
    lines: list[str] = [
        "# Paper A/B report (M8)",
        "",
        f"- **ab_mode:** `{result.ab_mode}`",
        f"- **cycles:** {result.cycles}",
        f"- **seed:** {result.seed}",
        f"- **started_at:** {result.started_at.isoformat()}",
        f"- **finished_at:** {result.finished_at.isoformat()}",
        f"- **MODE remains:** `{gate.mode_remains}` (live_enabled={gate.live_enabled})",
        "",
        "## Arm metrics",
        "",
    ]
    for name, metrics in result.arms.items():
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("```")
        lines.extend(metrics.summary_lines())
        lines.append("```")
        lines.append("")

    lines.append("## §13 gate check")
    lines.append("")
    lines.append(f"**Overall:** `{'PASS' if gate.passed else 'FAIL'}`")
    lines.append("")
    lines.append("| Check | Arm | Result | Detail |")
    lines.append("|---|---|---|---|")
    for c in gate.checks:
        mark = "PASS" if c.passed else "FAIL"
        lines.append(f"| `{c.name}` | `{c.applies_to}` | **{mark}** | {c.detail} |")
    lines.append("")
    lines.append(gate.summary)
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- This harness runs **synthetic/mock cycles** for CI and local comparison — "
        "it is **not** a substitute for the full §13 paper window on Exness MT5 demo."
    )
    lines.append(
        "- A gate **PASS** here still leaves **`MODE=paper`**. Live capital requires "
        "explicit human approval after a documented paper window."
    )
    lines.append("")
    return "\n".join(lines)


def _trade_dict(trade: ClosedPaperTrade) -> dict[str, Any]:
    raw = asdict(trade)
    raw["arm"] = trade.arm.value
    raw["entry_time"] = trade.entry_time.isoformat()
    raw["exit_time"] = trade.exit_time.isoformat()
    return raw


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")
