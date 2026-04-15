"""Network design checks aligned with CAF landing zone patterns."""

from __future__ import annotations

import ipaddress

from netinspect.analysis.findings import (
    AnalysisReport,
    Category,
    Finding,
    Severity,
)
from netinspect.models.types import Topology

CAT = Category.DESIGN


def check_design(topology: Topology, report: AnalysisReport) -> None:
    """Run all network design checks."""
    _check_address_space_overlaps(topology, report)
    _check_peering_asymmetry(topology, report)
    _check_hub_spoke_pattern(topology, report)
    _check_subnet_sizing(topology, report)
    _check_dns_configuration(topology, report)
    _check_missing_route_propagation(topology, report)


def _check_address_space_overlaps(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CAF — Address spaces should not overlap between peered VNets."""
    # Build VNet address networks
    vnet_networks: dict[str, list[ipaddress.IPv4Network]] = {}
    for vnet in topology.vnets:
        nets = []
        for space in vnet.address_spaces:
            try:
                nets.append(ipaddress.ip_network(space, strict=False))
            except ValueError:
                continue
        vnet_networks[vnet.name] = nets

    # Check all peered pairs
    checked: set[tuple[str, str]] = set()
    for vnet in topology.vnets:
        for peering in vnet.peerings:
            pair = tuple(sorted([vnet.name, peering.remote_vnet_name]))
            if pair in checked:
                continue
            checked.add(pair)

            nets_a = vnet_networks.get(vnet.name, [])
            nets_b = vnet_networks.get(peering.remote_vnet_name, [])

            for a in nets_a:
                for b in nets_b:
                    if a.overlaps(b):
                        report.add(Finding(
                            severity=Severity.CRITICAL,
                            category=CAT,
                            title="Address space overlap between peered VNets",
                            description=(
                                f"VNet '{vnet.name}' ({a}) overlaps with "
                                f"peered VNet '{peering.remote_vnet_name}' "
                                f"({b}). This can cause routing issues."
                            ),
                            recommendation=(
                                "Re-address one of the VNets to eliminate "
                                "overlapping ranges."
                            ),
                            resource_id=peering.id,
                            resource_name=f"{vnet.name} <-> {peering.remote_vnet_name}",
                        ))

    # Also check all VNet pairs (not just peered) for potential issues
    vnet_list = list(vnet_networks.items())
    for i, (name_a, nets_a) in enumerate(vnet_list):
        for name_b, nets_b in vnet_list[i + 1:]:
            pair = tuple(sorted([name_a, name_b]))
            if pair in checked:
                continue
            for a in nets_a:
                for b in nets_b:
                    if a.overlaps(b):
                        report.add(Finding(
                            severity=Severity.WARNING,
                            category=CAT,
                            title="Address space overlap between VNets",
                            description=(
                                f"VNet '{name_a}' ({a}) overlaps with "
                                f"VNet '{name_b}' ({b}). These VNets "
                                f"cannot be peered and routing may "
                                f"conflict via gateways."
                            ),
                            recommendation=(
                                "Plan address spaces to avoid overlaps "
                                "per CAF IP addressing guidelines."
                            ),
                            resource_name=f"{name_a} / {name_b}",
                        ))


def _check_peering_asymmetry(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CAF — Peering settings should be symmetric where expected."""
    peering_map: dict[str, dict] = {}
    for vnet in topology.vnets:
        for p in vnet.peerings:
            key = f"{vnet.name}->{p.remote_vnet_name}"
            peering_map[key] = {
                "vnet": vnet.name,
                "remote": p.remote_vnet_name,
                "forwarding": p.allow_forwarded_traffic,
                "gateway_transit": p.allow_gateway_transit,
                "use_remote_gw": p.use_remote_gateways,
                "peering": p,
            }

    checked: set[tuple[str, str]] = set()
    for vnet in topology.vnets:
        for p in vnet.peerings:
            pair = tuple(sorted([vnet.name, p.remote_vnet_name]))
            if pair in checked:
                continue
            checked.add(pair)

            fwd_key = f"{vnet.name}->{p.remote_vnet_name}"
            rev_key = f"{p.remote_vnet_name}->{vnet.name}"
            fwd = peering_map.get(fwd_key)
            rev = peering_map.get(rev_key)

            if not fwd or not rev:
                continue

            # If one side allows gateway transit, the other should use
            # remote gateways (or vice versa)
            if fwd["gateway_transit"] and not rev["use_remote_gw"]:
                report.add(Finding(
                    severity=Severity.WARNING,
                    category=CAT,
                    title="Peering gateway transit mismatch",
                    description=(
                        f"'{vnet.name}' allows gateway transit to "
                        f"'{p.remote_vnet_name}', but the remote side "
                        f"doesn't use remote gateways. Gateway routes "
                        f"won't propagate."
                    ),
                    recommendation=(
                        "Enable 'Use Remote Gateways' on the spoke "
                        "side when the hub allows gateway transit."
                    ),
                    resource_id=p.id,
                    resource_name=p.name,
                ))

            # Forwarding should typically be enabled on both sides
            if fwd["forwarding"] != rev["forwarding"]:
                report.add(Finding(
                    severity=Severity.INFO,
                    category=CAT,
                    title="Asymmetric forwarding in peering",
                    description=(
                        f"Forwarded traffic is "
                        f"{'allowed' if fwd['forwarding'] else 'blocked'} "
                        f"from '{vnet.name}' but "
                        f"{'allowed' if rev['forwarding'] else 'blocked'} "
                        f"from '{p.remote_vnet_name}'. This may be "
                        f"intentional for hub-spoke, but verify."
                    ),
                    recommendation=(
                        "Ensure forwarding settings match your "
                        "transit routing design."
                    ),
                    resource_id=p.id,
                    resource_name=p.name,
                ))


def _check_hub_spoke_pattern(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CAF — Identify if a hub-spoke pattern is used and validate it."""
    if len(topology.vnets) < 3:
        return  # Too few VNets for meaningful hub-spoke analysis

    # Find potential hubs (VNets with the most peerings)
    max_peerings = max(len(v.peerings) for v in topology.vnets)
    if max_peerings < 2:
        return

    hubs = [v for v in topology.vnets if len(v.peerings) == max_peerings]
    spokes = [v for v in topology.vnets if v not in hubs]

    for hub in hubs:
        # Check if hub has a gateway
        hub_has_gw = any(
            gw.vnet_id and gw.vnet_id == hub.id
            for gw in topology.vpn_gateways
        )

        if hub_has_gw:
            # Check if gateway transit is enabled for spokes
            for p in hub.peerings:
                if not p.allow_gateway_transit:
                    report.add(Finding(
                        severity=Severity.WARNING,
                        category=CAT,
                        title="Hub peering without gateway transit",
                        description=(
                            f"Hub VNet '{hub.name}' has a gateway but "
                            f"peering '{p.name}' to "
                            f"'{p.remote_vnet_name}' does not allow "
                            f"gateway transit."
                        ),
                        recommendation=(
                            "Enable gateway transit on hub peerings "
                            "to propagate on-prem routes to spokes."
                        ),
                        resource_id=p.id,
                        resource_name=p.name,
                    ))

        # Check spoke-to-spoke via hub
        spoke_peerings = set()
        for s in spokes:
            for p in s.peerings:
                spoke_peerings.add(
                    tuple(sorted([s.name, p.remote_vnet_name]))
                )
        spoke_names = {s.name for s in spokes}
        for pair in spoke_peerings:
            if pair[0] in spoke_names and pair[1] in spoke_names:
                report.add(Finding(
                    severity=Severity.INFO,
                    category=CAT,
                    title="Direct spoke-to-spoke peering detected",
                    description=(
                        f"VNets '{pair[0]}' and '{pair[1]}' are "
                        f"directly peered (spoke-to-spoke). In a "
                        f"hub-spoke design, spoke traffic should "
                        f"route through the hub."
                    ),
                    recommendation=(
                        "Consider routing spoke-to-spoke traffic "
                        "through a hub NVA/Firewall for inspection."
                    ),
                    resource_name=f"{pair[0]} <-> {pair[1]}",
                ))


def _check_subnet_sizing(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CAF — Subnets should not be too small or too large."""
    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            try:
                net = ipaddress.ip_network(
                    subnet.address_prefix, strict=False
                )
            except ValueError:
                continue

            prefix = net.prefixlen
            # Azure reserves 5 IPs per subnet
            usable = net.num_addresses - 5

            if prefix > 28 and subnet.name.lower() not in (
                "gatewaysubnet", "azurebastionsubnet",
            ):
                report.add(Finding(
                    severity=Severity.WARNING,
                    category=CAT,
                    title="Very small subnet",
                    description=(
                        f"Subnet '{subnet.name}' in '{vnet.name}' "
                        f"is /{prefix} ({usable} usable IPs). This "
                        f"limits future growth."
                    ),
                    recommendation=(
                        "Plan for at least /27 or /26 subnets to "
                        "allow scaling."
                    ),
                    resource_id=subnet.id,
                    resource_name=f"{vnet.name}/{subnet.name}",
                ))


def _check_dns_configuration(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CAF — VNets should have consistent DNS configuration."""
    dns_configs = set()
    for vnet in topology.vnets:
        dns_key = tuple(sorted(vnet.dns_servers)) or ("azure-default",)
        dns_configs.add(dns_key)

    if len(dns_configs) > 1 and len(topology.vnets) > 1:
        report.add(Finding(
            severity=Severity.INFO,
            category=CAT,
            title="Inconsistent DNS configuration across VNets",
            description=(
                "VNets have different DNS server configurations. "
                "This can cause name resolution inconsistencies "
                "for peered workloads."
            ),
            recommendation=(
                "Use consistent DNS settings across peered VNets, "
                "or leverage Azure Private DNS Zones for unified "
                "name resolution."
            ),
        ))


def _check_missing_route_propagation(
    topology: Topology, report: AnalysisReport,
) -> None:
    """CAF — Route tables with BGP disabled may drop gateway routes."""
    for rt in topology.route_tables:
        if rt.disable_bgp_route_propagation:
            report.add(Finding(
                severity=Severity.INFO,
                category=CAT,
                title="BGP route propagation disabled",
                description=(
                    f"Route table '{rt.name}' has BGP route "
                    f"propagation disabled. On-premises routes "
                    f"learned via gateway will not reach subnets "
                    f"using this table."
                ),
                recommendation=(
                    "This is correct for forced tunneling "
                    "scenarios. Verify this is intentional."
                ),
                resource_id=rt.id,
                resource_name=rt.name,
            ))
