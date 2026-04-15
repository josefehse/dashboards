"""Main analysis orchestrator — runs all CAF/WAF checks."""

from __future__ import annotations

from netinspect.analysis.checks_cost import check_cost
from netinspect.analysis.checks_design import check_design
from netinspect.analysis.checks_lb import check_load_balancers
from netinspect.analysis.checks_reliability import check_reliability
from netinspect.analysis.checks_security import check_security
from netinspect.analysis.findings import AnalysisReport
from netinspect.models.types import Topology


def analyze_topology(topology: Topology) -> AnalysisReport:
    """Run all CAF/WAF analysis checks against the topology."""
    report = AnalysisReport()

    check_security(topology, report)
    check_reliability(topology, report)
    check_design(topology, report)
    check_cost(topology, report)
    check_load_balancers(topology, report)

    return report
