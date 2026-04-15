"""Reachability analysis — combines routing and NSG evaluation.

Answers the question: "Can traffic from subnet A reach IP B on port P?"
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netinspect.analysis.routing import (
    EffectiveRoute,
    resolve_next_hop,
)
from netinspect.analysis.security import SecurityVerdict, evaluate_nsg
from netinspect.models.types import Topology


@dataclass
class ReachabilityResult:
    """Full reachability analysis result."""

    reachable: bool
    source_vnet: str
    source_subnet: str
    dest_ip: str
    dest_port: int
    protocol: str

    # Routing
    next_hop: EffectiveRoute | None = None
    route_detail: str = ""

    # NSG evaluation
    outbound_nsg: SecurityVerdict | None = None
    inbound_nsg: SecurityVerdict | None = None

    # NAT
    nat_gateway: str | None = None

    # Summary
    steps: list[str] = field(default_factory=list)


def check_reachability(
    topology: Topology,
    source_subnet_id: str,
    dest_ip: str,
    dest_port: int,
    protocol: str = "TCP",
    source_ip: str | None = None,
) -> ReachabilityResult:
    """Check if traffic can flow from a source subnet to a destination.

    Evaluates:
    1. Routing — what is the next hop?
    2. Outbound NSG — does the source subnet's NSG allow it?
    3. Inbound NSG — does the destination subnet's NSG allow it?
       (only if destination is within a discovered subnet)
    """
    # Find source info
    src_vnet, src_subnet = _find_subnet(topology, source_subnet_id)
    if not src_vnet or not src_subnet:
        return ReachabilityResult(
            reachable=False,
            source_vnet="Unknown",
            source_subnet="Unknown",
            dest_ip=dest_ip,
            dest_port=dest_port,
            protocol=protocol,
            steps=["❌ Source subnet not found in topology"],
        )

    if not source_ip:
        # Use the first IP in the subnet range as a placeholder
        import ipaddress

        net = ipaddress.ip_network(src_subnet.address_prefix, strict=False)
        source_ip = str(list(net.hosts())[0]) if net.num_addresses > 1 else str(net.network_address)

    result = ReachabilityResult(
        reachable=False,
        source_vnet=src_vnet.name,
        source_subnet=src_subnet.name,
        dest_ip=dest_ip,
        dest_port=dest_port,
        protocol=protocol,
    )

    steps = result.steps

    # Step 1: Resolve next hop
    steps.append(
        f"🔍 Source: {src_vnet.name}/{src_subnet.name} "
        f"({src_subnet.address_prefix})"
    )
    steps.append(f"🎯 Destination: {dest_ip}:{dest_port}/{protocol}")

    next_hop = resolve_next_hop(topology, source_subnet_id, dest_ip)
    result.next_hop = next_hop

    if next_hop is None:
        steps.append("❌ No matching route found — traffic will be dropped")
        return result

    hop_desc = next_hop.next_hop_type
    if next_hop.next_hop_ip:
        hop_desc += f" ({next_hop.next_hop_ip})"
    if next_hop.next_hop_detail:
        hop_desc += f" → {next_hop.next_hop_detail}"
    result.route_detail = hop_desc
    steps.append(f"🔀 Route: {next_hop.address_prefix} → {hop_desc}")

    if next_hop.next_hop_type == "None":
        steps.append("❌ Next hop is None — traffic will be dropped")
        return result

    # Check NAT Gateway for internet-bound traffic
    if next_hop.next_hop_type == "Internet" and src_subnet.nat_gateway_id:
        for ng in topology.nat_gateways:
            if ng.id == src_subnet.nat_gateway_id:
                result.nat_gateway = ng.name
                steps.append(f"🌐 NAT Gateway: {ng.name} (SNAT applied)")
                break

    # Step 2: Evaluate outbound NSG on source subnet
    outbound = evaluate_nsg(
        topology, source_subnet_id, "Outbound",
        source_ip, dest_ip, dest_port, protocol,
    )
    result.outbound_nsg = outbound

    if outbound is None:
        steps.append("🛡️ Outbound NSG: No NSG on source subnet")
    elif not outbound.allowed:
        steps.append(
            f"🛡️ Outbound NSG ({outbound.nsg_name}): {outbound.reason}"
        )
        steps.append("❌ Traffic blocked by outbound NSG")
        return result
    else:
        steps.append(
            f"🛡️ Outbound NSG ({outbound.nsg_name}): {outbound.reason}"
        )

    # Step 3: Find destination subnet and evaluate inbound NSG
    dest_subnet_id = _find_subnet_for_ip(topology, dest_ip)
    if dest_subnet_id:
        inbound = evaluate_nsg(
            topology, dest_subnet_id, "Inbound",
            source_ip, dest_ip, dest_port, protocol,
        )
        result.inbound_nsg = inbound

        if inbound is None:
            steps.append("🛡️ Inbound NSG: No NSG on destination subnet")
        elif not inbound.allowed:
            steps.append(
                f"🛡️ Inbound NSG ({inbound.nsg_name}): {inbound.reason}"
            )
            steps.append("❌ Traffic blocked by inbound NSG")
            return result
        else:
            steps.append(
                f"🛡️ Inbound NSG ({inbound.nsg_name}): {inbound.reason}"
            )
    else:
        steps.append(
            "🛡️ Inbound NSG: Destination not in a discovered subnet "
            "(external or cross-subscription)"
        )

    # All checks passed
    result.reachable = True
    steps.append("✅ Traffic should be able to reach the destination")
    return result


def _find_subnet(topology: Topology, subnet_id: str):
    """Find a VNet and Subnet by subnet ID."""
    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            if subnet.id == subnet_id:
                return vnet, subnet
    return None, None


def _find_subnet_for_ip(topology: Topology, ip: str) -> str | None:
    """Find the subnet ID containing a given IP address."""
    import ipaddress

    addr = ipaddress.ip_address(ip)
    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            try:
                net = ipaddress.ip_network(
                    subnet.address_prefix, strict=False
                )
                if addr in net:
                    return subnet.id
            except ValueError:
                continue
    return None
