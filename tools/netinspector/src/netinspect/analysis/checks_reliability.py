"""Reliability analysis checks aligned with WAF Reliability pillar."""

from __future__ import annotations

from netinspect.analysis.findings import (
    AnalysisReport,
    Category,
    Finding,
    Severity,
)
from netinspect.models.types import Topology

CAT = Category.RELIABILITY


def check_reliability(topology: Topology, report: AnalysisReport) -> None:
    """Run all reliability checks against the topology."""
    _check_vpn_gateway_redundancy(topology, report)
    _check_connection_status(topology, report)
    _check_peering_state(topology, report)
    _check_expressroute_redundancy(topology, report)
    _check_single_nat_gateway(topology, report)
    _check_gateway_subnet_exists(topology, report)


def _check_vpn_gateway_redundancy(
    topology: Topology, report: AnalysisReport,
) -> None:
    """RE:05 — VPN Gateways should be active-active for HA."""
    for gw in topology.vpn_gateways:
        if gw.gateway_type != "Vpn":
            continue
        if not gw.active_active:
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title="VPN Gateway not active-active",
                description=(
                    f"VPN Gateway '{gw.name}' is in active-standby "
                    f"mode. Failover to standby takes 60-90 seconds "
                    f"and causes connection drops."
                ),
                recommendation=(
                    "Enable active-active configuration for "
                    "higher availability and faster failover."
                ),
                resource_id=gw.id,
                resource_name=gw.name,
                waf_pillar="RE:05",
            ))

        # Check SKU level
        basic_skus = {"Basic", "VpnGw1"}
        if gw.sku in basic_skus:
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title="VPN Gateway using low-tier SKU",
                description=(
                    f"VPN Gateway '{gw.name}' uses SKU '{gw.sku}'. "
                    f"Basic and VpnGw1 offer limited throughput and "
                    f"no zone redundancy."
                ),
                recommendation=(
                    "Consider VpnGw2AZ or higher for production "
                    "workloads requiring zone-redundant gateways."
                ),
                resource_id=gw.id,
                resource_name=gw.name,
                waf_pillar="RE:05",
            ))


def _check_connection_status(
    topology: Topology, report: AnalysisReport,
) -> None:
    """RE:07 — Monitor connection health."""
    for gw in topology.vpn_gateways:
        for conn in gw.connections:
            if conn.status not in ("Connected", "Unknown"):
                report.add(Finding(
                    severity=Severity.CRITICAL,
                    category=CAT,
                    title="VPN connection not connected",
                    description=(
                        f"Connection '{conn.name}' on gateway "
                        f"'{gw.name}' has status '{conn.status}'."
                    ),
                    recommendation=(
                        "Investigate the connection failure. Check "
                        "shared keys, remote gateway reachability, "
                        "and IPsec/IKE parameters."
                    ),
                    resource_id=conn.id,
                    resource_name=conn.name,
                    waf_pillar="RE:07",
                ))


def _check_peering_state(
    topology: Topology, report: AnalysisReport,
) -> None:
    """RE:05 — Peerings should be Connected."""
    for vnet in topology.vnets:
        for peering in vnet.peerings:
            if peering.state.value != "Connected":
                report.add(Finding(
                    severity=Severity.CRITICAL,
                    category=CAT,
                    title="VNet peering not connected",
                    description=(
                        f"Peering '{peering.name}' from '{vnet.name}' "
                        f"to '{peering.remote_vnet_name}' is in state "
                        f"'{peering.state.value}'."
                    ),
                    recommendation=(
                        "Verify peering is configured on both sides. "
                        "Ensure address spaces don't overlap and that "
                        "the remote VNet exists."
                    ),
                    resource_id=peering.id,
                    resource_name=peering.name,
                    waf_pillar="RE:05",
                ))


def _check_expressroute_redundancy(
    topology: Topology, report: AnalysisReport,
) -> None:
    """RE:05 — ExpressRoute should have redundant circuits or VPN backup."""
    er_circuits = topology.expressroute_circuits
    vpn_gateways = [
        gw for gw in topology.vpn_gateways if gw.gateway_type == "Vpn"
    ]
    er_gateways = [
        gw for gw in topology.vpn_gateways
        if gw.gateway_type == "ExpressRoute"
    ]

    if er_gateways and len(er_circuits) == 1 and not vpn_gateways:
        report.add(Finding(
            severity=Severity.WARNING,
            category=CAT,
            title="Single ExpressRoute circuit with no VPN backup",
            description=(
                f"Only one ExpressRoute circuit "
                f"('{er_circuits[0].name}') exists with no site-to-site "
                f"VPN as backup. A provider outage will cause "
                f"complete loss of hybrid connectivity."
            ),
            recommendation=(
                "Add a second ExpressRoute circuit from a different "
                "peering location, or deploy a VPN Gateway as "
                "failover path."
            ),
            resource_id=er_circuits[0].id,
            resource_name=er_circuits[0].name,
            waf_pillar="RE:05",
        ))


def _check_single_nat_gateway(
    topology: Topology, report: AnalysisReport,
) -> None:
    """RE:05 — NAT Gateways are zone-resilient but check PIP count."""
    for ng in topology.nat_gateways:
        if len(ng.public_ip_addresses) < 1:
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title="NAT Gateway with no public IPs",
                description=(
                    f"NAT Gateway '{ng.name}' has no public IPs "
                    f"assigned. Outbound connectivity will fail."
                ),
                recommendation="Assign at least one public IP address.",
                resource_id=ng.id,
                resource_name=ng.name,
                waf_pillar="RE:05",
            ))


def _check_gateway_subnet_exists(
    topology: Topology, report: AnalysisReport,
) -> None:
    """RE:05 — VNets with gateways should have proper GatewaySubnet sizing."""
    for gw in topology.vpn_gateways:
        if not gw.vnet_id:
            continue
        vnet_name = gw.vnet_id.split("/")[-1]
        # Find the VNet
        target_vnet = None
        for vnet in topology.vnets:
            if vnet.id == gw.vnet_id:
                target_vnet = vnet
                break
        if not target_vnet:
            continue

        gw_subnet = None
        for s in target_vnet.subnets:
            if s.name.lower() == "gatewaysubnet":
                gw_subnet = s
                break

        if gw_subnet:
            # Check subnet size — /27 minimum recommended, /26 for ER
            prefix_len = int(gw_subnet.address_prefix.split("/")[1])
            if prefix_len > 27:
                report.add(Finding(
                    severity=Severity.WARNING,
                    category=CAT,
                    title="GatewaySubnet too small",
                    description=(
                        f"GatewaySubnet in '{vnet_name}' is "
                        f"/{prefix_len}. Microsoft recommends at "
                        f"least /27 (or /26 for ExpressRoute)."
                    ),
                    recommendation=(
                        "Resize GatewaySubnet to /27 or /26 to "
                        "allow for future gateway configurations."
                    ),
                    resource_id=gw_subnet.id,
                    resource_name=f"{vnet_name}/GatewaySubnet",
                    waf_pillar="RE:05",
                ))
