"""M8 paper A/B harness — runner, gates, report, CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autotrader.__main__ import main
from autotrader.config import (
    AbMode,
    PaperAbConfig,
    PaperGateThresholds,
    load_config,
    load_yaml_config,
)
from autotrader.paper_ab.gates import check_section13_gates
from autotrader.paper_ab.metrics import compute_arm_metrics
from autotrader.paper_ab.report import build_report_dict, write_ab_report
from autotrader.paper_ab.rules_arm import ai_scripted_decision, rules_only_risk_payload
from autotrader.paper_ab.runner import PaperAbRunner, run_paper_ab
from autotrader.paper_ab.scenarios import generate_synthetic_cycles, load_cycles_fixture
from autotrader.paper_ab.types import ArmName, ClosedPaperTrade

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "paper_ab_cycles.json"


def test_yaml_paper_ab_defaults() -> None:
    cfg = load_yaml_config()
    assert cfg.paper_ab.ab_mode == AbMode.BOTH
    assert cfg.paper_ab.cycles == 50
    assert cfg.paper_ab.gates.min_closed_trades == 80
    assert cfg.paper_ab.gates.min_weeks == 2
    assert cfg.paper_ab.gates.max_drawdown_pct == 8.0
    assert cfg.paper_ab.gates.max_bad_json_rate_pct == 3.0
    assert cfg.paper_ab.gates.ab_dd_tolerance_pp == 1.0


def test_ab_mode_enum_values() -> None:
    assert AbMode.RULES_ONLY.value == "rules_only"
    assert AbMode.RULES_PLUS_AI.value == "rules_plus_ai"
    assert AbMode.BOTH.value == "both"


def test_fixture_cycles_load() -> None:
    cycles = load_cycles_fixture(FIXTURE)
    assert len(cycles) == 6
    assert cycles[0].has_signal is True
    assert cycles[2].ai_outcome == "bad_json"
    assert cycles[3].has_signal is False


def test_rules_only_payload_from_signal() -> None:
    cycle = load_cycles_fixture(FIXTURE)[0]
    payload = rules_only_risk_payload(cycle, idempotency_key="k1")
    assert payload["action"] == "enter"
    assert payload["symbol"] == "EURUSD"
    assert payload["requested_risk_pct"] == 0.5
    assert payload["stop_distance_price"] == pytest.approx(0.005)


def test_ai_scripted_bad_json_and_skip() -> None:
    cycles = load_cycles_fixture(FIXTURE)
    reason, payload = ai_scripted_decision(cycles[2], idempotency_key="k")
    assert reason == "bad_json"
    assert payload is None
    reason2, payload2 = ai_scripted_decision(cycles[1], idempotency_key="k")
    assert reason2 == "decision_skip"
    assert payload2 is not None
    assert payload2["action"] == "skip"


def test_runner_both_arms_on_fixture() -> None:
    result = run_paper_ab(cycles=6, ab_mode=AbMode.BOTH, seed=1, fixture_path=FIXTURE)
    assert result.ab_mode == "both"
    assert ArmName.RULES_ONLY.value in result.arms
    assert ArmName.RULES_PLUS_AI.value in result.arms

    rules = result.arms["rules_only"]
    ai = result.arms["rules_plus_ai"]

    # Fixture: signals on cycles 0,1,2,4,5 (5 signals); rules-only takes all 5
    assert rules.signals_seen == 5
    assert rules.trades == 5
    # AI skips cycle 1, bad_json on cycle 2 → 3 enters
    assert ai.agent4_calls == 5
    assert ai.bad_json_count == 1
    assert ai.bad_json_rate == pytest.approx(0.2)
    assert ai.trades == 3
    # AI takes a subset — fewer or equal trades vs rules-only
    assert ai.trades <= rules.trades


def test_runner_rules_only_mode() -> None:
    result = run_paper_ab(cycles=6, ab_mode="rules_only", fixture_path=FIXTURE)
    assert list(result.arms.keys()) == ["rules_only"]
    assert result.arms["rules_only"].agent4_calls == 0
    assert result.arms["rules_only"].bad_json_rate == 0.0


def test_runner_synthetic_seed_reproducible() -> None:
    a = run_paper_ab(cycles=40, ab_mode=AbMode.BOTH, seed=99)
    b = run_paper_ab(cycles=40, ab_mode=AbMode.BOTH, seed=99)
    assert a.arms["rules_only"].trades == b.arms["rules_only"].trades
    assert a.arms["rules_plus_ai"].expectancy_r == b.arms["rules_plus_ai"].expectancy_r
    assert a.arms["rules_plus_ai"].bad_json_count == b.arms["rules_plus_ai"].bad_json_count


def test_metrics_expectancy_and_dd() -> None:
    from datetime import UTC, datetime

    trades = [
        ClosedPaperTrade(
            cycle_index=0,
            symbol="EURUSD",
            side="long",
            entry_time=datetime(2026, 1, 5, 15, tzinfo=UTC),
            exit_time=datetime(2026, 1, 5, 16, tzinfo=UTC),
            entry_price=1.1,
            exit_price=1.11,
            stop_price=1.09,
            pnl_r=1.0,
            pnl=50.0,
            reason="t",
            arm=ArmName.RULES_ONLY,
        ),
        ClosedPaperTrade(
            cycle_index=1,
            symbol="EURUSD",
            side="long",
            entry_time=datetime(2026, 1, 5, 17, tzinfo=UTC),
            exit_time=datetime(2026, 1, 5, 18, tzinfo=UTC),
            entry_price=1.1,
            exit_price=1.09,
            stop_price=1.09,
            pnl_r=-1.0,
            pnl=-50.0,
            reason="t",
            arm=ArmName.RULES_ONLY,
        ),
    ]
    m = compute_arm_metrics(
        arm=ArmName.RULES_ONLY,
        trades=trades,
        starting_equity=10_000.0,
        agent4_calls=0,
        bad_json_count=0,
    )
    assert m.trades == 2
    assert m.expectancy_r == pytest.approx(0.0)
    assert m.net_return_pct == pytest.approx(0.0)
    assert m.max_drawdown_pct >= 0.0


def test_gate_checker_fail_on_small_sample() -> None:
    result = run_paper_ab(cycles=6, ab_mode=AbMode.BOTH, fixture_path=FIXTURE)
    gate = check_section13_gates(result)
    assert gate.live_enabled is False
    assert gate.mode_remains == "paper"
    # 6-cycle fixture cannot meet 80 trades / 2 weeks
    assert gate.passed is False
    names = {c.name for c in gate.checks}
    assert "min_sample" in names


def test_gate_checker_pass_with_relaxed_thresholds(tmp_path: Path) -> None:
    # Generate enough synthetic cycles with strong positive bias for a local pass
    cfg = load_config()
    cfg = cfg.model_copy(
        update={
            "paper_ab": PaperAbConfig(
                ab_mode=AbMode.BOTH,
                cycles=200,
                seed=7,
                positive_bias=0.72,
                bad_json_rate=0.01,
                ai_skip_rate=0.05,
                signal_rate=0.7,
                gates=PaperGateThresholds(
                    min_closed_trades=20,
                    min_weeks=1,
                    max_drawdown_pct=8.0,
                    min_net_return_pct=0.0,
                    min_expectancy_r=0.0,
                    min_reward_risk=0.5,
                    max_bad_json_rate_pct=5.0,
                    ab_dd_tolerance_pp=2.0,
                ),
            )
        }
    )
    runner = PaperAbRunner(config=cfg, seed=7)
    result = runner.run(cycles=200, ab_mode=AbMode.BOTH)
    gate = check_section13_gates(result, thresholds=cfg.paper_ab.gates)
    assert gate.live_enabled is False
    assert gate.mode_remains == "paper"
    # Soft assertion: with relaxed thresholds + positive bias, expect pass
    assert gate.passed is True, gate.summary_lines()

    paths = write_ab_report(result, gate, output_dir=tmp_path, basename="test-pass")
    assert paths["json"].is_file()
    assert paths["markdown"].is_file()
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["gates"]["live_enabled"] is False
    assert payload["kind"] == "paper_ab_report"


def test_gate_never_enables_live() -> None:
    result = run_paper_ab(cycles=10, ab_mode=AbMode.BOTH, seed=1)
    # Even if we forge a "pass" via empty checks path, live_enabled stays false
    gate = check_section13_gates(
        result,
        thresholds=PaperGateThresholds(
            min_closed_trades=1,
            min_weeks=1,
            max_drawdown_pct=100.0,
            min_net_return_pct=-100.0,
            min_expectancy_r=-100.0,
            min_reward_risk=0.0,
            max_bad_json_rate_pct=100.0,
            ab_dd_tolerance_pp=100.0,
        ),
    )
    assert gate.live_enabled is False
    assert gate.mode_remains == "paper"


def test_report_dict_shape() -> None:
    result = run_paper_ab(cycles=6, ab_mode=AbMode.BOTH, fixture_path=FIXTURE)
    gate = check_section13_gates(result)
    payload = build_report_dict(result, gate)
    assert "arms" in payload
    assert "gates" in payload
    assert payload["gates"]["live_enabled"] is False


def test_cli_paper_ab_cycles(capsys, tmp_path: Path) -> None:
    code = main(
        [
            "paper-ab",
            "--cycles",
            "6",
            "--fixture",
            str(FIXTURE),
            "--output-dir",
            str(tmp_path),
            "--basename",
            "cli-run",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "MODE=paper" in out
    assert "ab_mode=both" in out
    assert "live_enabled=false" in out
    assert "section13_pass=" in out
    assert (tmp_path / "cli-run.json").is_file()
    assert (tmp_path / "cli-run.md").is_file()


def test_cli_paper_ab_module_entry(capsys, tmp_path: Path) -> None:
    from autotrader.paper_ab.cli import main as paper_main

    code = paper_main(
        [
            "--cycles",
            "6",
            "--ab-mode",
            "rules_only",
            "--fixture",
            str(FIXTURE),
            "--output-dir",
            str(tmp_path),
            "--basename",
            "rules-only",
            "--no-write",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "arm=rules_only" in out
    assert "rules_plus_ai" not in out.split("--- §13 gates ---")[0]


def test_smoke_prints_ab_mode(capsys) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "ab_mode=" in out


def test_generate_synthetic_cycles_count() -> None:
    cycles = generate_synthetic_cycles(count=25, seed=3)
    assert len(cycles) == 25
    assert any(c.has_signal for c in cycles)


def test_example_report_committed() -> None:
    example = REPO_ROOT / "reports" / "examples" / "paper-ab-example.md"
    assert example.is_file()
    text = example.read_text(encoding="utf-8")
    assert "Paper A/B" in text
    assert "MODE" in text
    assert "live" in text.lower()


def test_gitignore_reports_except_examples() -> None:
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/reports/*" in gi
    assert "!/reports/examples/" in gi
