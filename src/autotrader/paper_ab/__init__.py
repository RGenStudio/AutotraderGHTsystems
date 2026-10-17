"""M8 paper trading A/B harness — rules-only vs rules+AI (synthetic/mock cycles)."""

from autotrader.paper_ab.gates import GateCheckResult, check_section13_gates
from autotrader.paper_ab.report import write_ab_report
from autotrader.paper_ab.runner import PaperAbRunner, run_paper_ab
from autotrader.paper_ab.types import AbRunResult, ArmMetrics, ArmName

__all__ = [
    "AbRunResult",
    "ArmMetrics",
    "ArmName",
    "GateCheckResult",
    "PaperAbRunner",
    "check_section13_gates",
    "run_paper_ab",
    "write_ab_report",
]
