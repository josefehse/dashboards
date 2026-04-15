"""Data types and base framework for CAF/WAF analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "Critical"
    WARNING = "Warning"
    INFO = "Info"


class Category(str, Enum):
    SECURITY = "Security"
    RELIABILITY = "Reliability"
    COST = "Cost Optimization"
    OPERATIONS = "Operational Excellence"
    DESIGN = "Network Design"


@dataclass
class Finding:
    """A single CAF/WAF finding."""

    severity: Severity
    category: Category
    title: str
    description: str
    recommendation: str
    resource_id: str = ""
    resource_name: str = ""
    waf_pillar: str = ""  # e.g. "SE:06", "RE:05"

    @property
    def severity_icon(self) -> str:
        return {
            Severity.CRITICAL: "🔴",
            Severity.WARNING: "🟡",
            Severity.INFO: "🔵",
        }[self.severity]


@dataclass
class AnalysisReport:
    """Container for all analysis findings."""

    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    def by_category(self, category: Category) -> list[Finding]:
        return [f for f in self.findings if f.category == category]

    def sorted_findings(self) -> list[Finding]:
        order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        return sorted(self.findings, key=lambda f: order[f.severity])
