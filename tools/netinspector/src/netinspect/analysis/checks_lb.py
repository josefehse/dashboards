"""Load Balancer and Application Gateway analysis checks."""

from __future__ import annotations

from netinspect.analysis.findings import (
    AnalysisReport,
    Category,
    Finding,
    Severity,
)
from netinspect.models.types import Topology


def check_load_balancers(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Run all load balancer and application gateway checks."""
    _check_lb_no_backend(topology, report)
    _check_lb_no_probes(topology, report)
    _check_lb_basic_sku(topology, report)
    _check_appgw_waf_disabled(topology, report)
    _check_appgw_waf_detection(topology, report)
    _check_appgw_no_backends(topology, report)


def _check_lb_no_backend(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Empty backend pools mean the LB isn't doing anything."""
    for lb in topology.load_balancers:
        empty = [bp for bp in lb.backend_pools if bp.ip_count == 0]
        if empty and lb.rules:
            names = ", ".join(bp.name for bp in empty)
            report.add(Finding(
                severity=Severity.WARNING,
                category=Category.RELIABILITY,
                title="Load balancer with empty backend pool",
                description=(
                    f"LB '{lb.name}' has rules but backend pool(s) "
                    f"'{names}' have no members. Traffic will fail."
                ),
                recommendation=(
                    "Add backend targets to the pool, or remove "
                    "unused LB rules."
                ),
                resource_id=lb.id,
                resource_name=lb.name,
                waf_pillar="RE:05",
            ))


def _check_lb_no_probes(
    topology: Topology, report: AnalysisReport,
) -> None:
    """LBs with rules but no health probes can't detect failures."""
    for lb in topology.load_balancers:
        if lb.rules and not lb.probes:
            report.add(Finding(
                severity=Severity.WARNING,
                category=Category.RELIABILITY,
                title="Load balancer without health probes",
                description=(
                    f"LB '{lb.name}' has {len(lb.rules)} rules but "
                    f"no health probes configured."
                ),
                recommendation=(
                    "Add health probes to detect backend failures "
                    "and remove unhealthy instances from rotation."
                ),
                resource_id=lb.id,
                resource_name=lb.name,
                waf_pillar="RE:07",
            ))


def _check_lb_basic_sku(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Basic SKU LBs lack zone redundancy and SLA."""
    for lb in topology.load_balancers:
        if lb.sku == "Basic":
            report.add(Finding(
                severity=Severity.WARNING,
                category=Category.RELIABILITY,
                title="Basic SKU load balancer",
                description=(
                    f"LB '{lb.name}' uses Basic SKU which has no "
                    f"SLA, no zone redundancy, and no NSG support."
                ),
                recommendation=(
                    "Migrate to Standard SKU for production "
                    "workloads. Basic LBs are being retired."
                ),
                resource_id=lb.id,
                resource_name=lb.name,
                waf_pillar="RE:05",
            ))


def _check_appgw_waf_disabled(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Application Gateways without WAF expose web apps."""
    for agw in topology.application_gateways:
        if not agw.waf_enabled:
            report.add(Finding(
                severity=Severity.WARNING,
                category=Category.SECURITY,
                title="Application Gateway without WAF",
                description=(
                    f"AppGW '{agw.name}' does not have Web "
                    f"Application Firewall enabled. Web apps are "
                    f"exposed to OWASP top-10 attacks."
                ),
                recommendation=(
                    "Enable WAF in Prevention mode, or deploy "
                    "a WAF_v2 SKU Application Gateway."
                ),
                resource_id=agw.id,
                resource_name=agw.name,
                waf_pillar="SE:06",
            ))


def _check_appgw_waf_detection(
    topology: Topology, report: AnalysisReport,
) -> None:
    """WAF in Detection mode only logs — doesn't block."""
    for agw in topology.application_gateways:
        if agw.waf_enabled and agw.waf_mode == "Detection":
            report.add(Finding(
                severity=Severity.WARNING,
                category=Category.SECURITY,
                title="WAF in Detection mode only",
                description=(
                    f"AppGW '{agw.name}' WAF is in Detection mode. "
                    f"Malicious requests are logged but NOT blocked."
                ),
                recommendation=(
                    "Switch WAF to Prevention mode to actively "
                    "block attacks."
                ),
                resource_id=agw.id,
                resource_name=agw.name,
                waf_pillar="SE:06",
            ))


def _check_appgw_no_backends(
    topology: Topology, report: AnalysisReport,
) -> None:
    """AppGW with empty backend pools."""
    for agw in topology.application_gateways:
        empty = [bp for bp in agw.backend_pools if bp.target_count == 0]
        if empty and agw.routing_rules:
            names = ", ".join(bp.name for bp in empty)
            report.add(Finding(
                severity=Severity.WARNING,
                category=Category.RELIABILITY,
                title="AppGW with empty backend pool",
                description=(
                    f"AppGW '{agw.name}' has routing rules but "
                    f"backend pool(s) '{names}' have no targets."
                ),
                recommendation=(
                    "Add backend targets or remove unused "
                    "routing rules."
                ),
                resource_id=agw.id,
                resource_name=agw.name,
                waf_pillar="RE:05",
            ))
