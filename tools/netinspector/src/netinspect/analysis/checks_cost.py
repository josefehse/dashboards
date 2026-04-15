"""Cost optimization checks aligned with WAF Cost pillar."""

from __future__ import annotations

from netinspect.analysis.findings import (
    AnalysisReport,
    Category,
    Finding,
    Severity,
)
from netinspect.models.types import Topology

CAT = Category.COST


def check_cost(topology: Topology, report: AnalysisReport) -> None:
    """Run all cost optimization checks."""
    _check_unassociated_public_ips(topology, report)
    _check_unused_route_tables(topology, report)
    _check_overprovisioned_gateways(topology, report)


def _check_unassociated_public_ips(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CO:07 — Unassociated PIPs still incur charges."""
    for pip in topology.public_ips:
        if not pip.associated_resource_id:
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title="Unassociated public IP",
                description=(
                    f"Public IP '{pip.name}' ({pip.ip_address}) is "
                    f"not associated with any resource. Standard SKU "
                    f"PIPs incur charges even when unattached."
                ),
                recommendation=(
                    "Delete the public IP if no longer needed, or "
                    "associate it with the intended resource."
                ),
                resource_id=pip.id,
                resource_name=pip.name,
                waf_pillar="CO:07",
            ))


def _check_unused_route_tables(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CO:07 — Route tables not attached to any subnet."""
    for rt in topology.route_tables:
        if not rt.associated_subnets:
            report.add(Finding(
                severity=Severity.INFO,
                category=CAT,
                title="Unused route table",
                description=(
                    f"Route table '{rt.name}' is not associated "
                    f"with any subnet."
                ),
                recommendation=(
                    "Remove unused route tables to reduce clutter "
                    "and management overhead."
                ),
                resource_id=rt.id,
                resource_name=rt.name,
                waf_pillar="CO:07",
            ))


def _check_overprovisioned_gateways(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CO:05 — Check for over-provisioned gateway SKUs."""
    high_skus = {
        "VpnGw4", "VpnGw5", "VpnGw4AZ", "VpnGw5AZ",
        "ErGw3AZ", "UltraPerformance",
    }
    for gw in topology.vpn_gateways:
        if gw.sku in high_skus:
            conn_count = len(gw.connections)
            if conn_count < 5:
                report.add(Finding(
                    severity=Severity.INFO,
                    category=CAT,
                    title="Potentially over-provisioned gateway",
                    description=(
                        f"Gateway '{gw.name}' uses SKU '{gw.sku}' "
                        f"but only has {conn_count} connections. "
                        f"High-tier SKUs are expensive."
                    ),
                    recommendation=(
                        "Review if a lower SKU would meet throughput "
                        "and connection requirements."
                    ),
                    resource_id=gw.id,
                    resource_name=gw.name,
                    waf_pillar="CO:05",
                ))
