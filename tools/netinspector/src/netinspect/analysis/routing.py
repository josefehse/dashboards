"""Effective route computation for Azure network topology.

Computes the effective route table for each subnet by combining:
1. System routes (VNet address space, peered VNets, 0.0.0.0/0 → Internet)
2. User-defined routes (UDRs) from associated route tables
3. Peering propagation effects (gateway transit, forwarded traffic)
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from netinspect.models.types import Topology


@dataclass
class EffectiveRoute:
    """A single effective route entry."""

    source: str  # "System", "User", "Peering", "Gateway"
    address_prefix: str
    next_hop_type: str
    next_hop_ip: str | None = None
    next_hop_detail: str | None = None  # Extra context (e.g. VNet name)
    active: bool = True  # False if overridden by a more specific route


@dataclass
class SubnetRouteInfo:
    """Effective routes for a specific subnet."""

    vnet_name: str
    subnet_name: str
    subnet_id: str
    subnet_prefix: str
    has_nat_gateway: bool = False
    nat_gateway_name: str | None = None
    routes: list[EffectiveRoute] = field(default_factory=list)


def compute_effective_routes(topology: Topology) -> list[SubnetRouteInfo]:
    """Compute effective routes for every subnet in the topology."""
    # Build lookup maps
    rt_map = {rt.id: rt for rt in topology.route_tables}
    ng_map = {ng.id: ng for ng in topology.nat_gateways}
    vnet_map = {v.id: v for v in topology.vnets}
    gw_map = {gw.vnet_id: gw for gw in topology.vpn_gateways if gw.vnet_id}

    results = []

    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            info = SubnetRouteInfo(
                vnet_name=vnet.name,
                subnet_name=subnet.name,
                subnet_id=subnet.id,
                subnet_prefix=subnet.address_prefix,
            )

            # Check NAT Gateway
            if subnet.nat_gateway_id and subnet.nat_gateway_id in ng_map:
                ng = ng_map[subnet.nat_gateway_id]
                info.has_nat_gateway = True
                info.nat_gateway_name = ng.name

            routes: list[EffectiveRoute] = []

            # 1. System routes: local VNet address spaces
            for addr_space in vnet.address_spaces:
                routes.append(EffectiveRoute(
                    source="System",
                    address_prefix=addr_space,
                    next_hop_type="VnetLocal",
                    next_hop_detail=vnet.name,
                ))

            # 2. System routes: peered VNets
            for peering in vnet.peerings:
                if peering.state.value != "Connected":
                    continue
                if not peering.allow_virtual_network_access:
                    continue
                remote = vnet_map.get(peering.remote_vnet_id)
                if remote:
                    for addr_space in remote.address_spaces:
                        routes.append(EffectiveRoute(
                            source="Peering",
                            address_prefix=addr_space,
                            next_hop_type="VNetPeering",
                            next_hop_detail=remote.name,
                        ))

            # 3. System route: default Internet route
            routes.append(EffectiveRoute(
                source="System",
                address_prefix="0.0.0.0/0",
                next_hop_type="Internet",
            ))

            # 4. VPN Gateway route (if VNet has a gateway)
            if vnet.id in gw_map:
                gw = gw_map[vnet.id]
                routes.append(EffectiveRoute(
                    source="Gateway",
                    address_prefix="(gateway learned)",
                    next_hop_type="VirtualNetworkGateway",
                    next_hop_detail=gw.name,
                ))

            # 5. User-defined routes override system routes
            if subnet.route_table_id and subnet.route_table_id in rt_map:
                rt = rt_map[subnet.route_table_id]
                for udr in rt.routes:
                    routes.append(EffectiveRoute(
                        source="User",
                        address_prefix=udr.address_prefix,
                        next_hop_type=udr.next_hop_type,
                        next_hop_ip=udr.next_hop_ip,
                    ))

            # Mark overridden routes
            info.routes = _resolve_route_precedence(routes)
            results.append(info)

    return results


def resolve_next_hop(
    topology: Topology,
    source_subnet_id: str,
    dest_ip: str,
) -> EffectiveRoute | None:
    """Determine the next hop for traffic from a subnet to a destination IP."""
    all_routes = compute_effective_routes(topology)

    for info in all_routes:
        if info.subnet_id != source_subnet_id:
            continue

        active_routes = [r for r in info.routes if r.active]
        match = _longest_prefix_match(active_routes, dest_ip)
        return match

    return None


def _resolve_route_precedence(
    routes: list[EffectiveRoute],
) -> list[EffectiveRoute]:
    """Apply Azure route precedence: UDR > Peering > System.

    For overlapping prefixes, more specific wins. For same prefix,
    User > Gateway > Peering > System.
    """
    priority = {"User": 0, "Gateway": 1, "Peering": 2, "System": 3}

    # Group by prefix
    prefix_groups: dict[str, list[EffectiveRoute]] = {}
    for r in routes:
        if r.address_prefix == "(gateway learned)":
            # Keep gateway-learned routes always active
            continue
        prefix_groups.setdefault(r.address_prefix, []).append(r)

    # For each prefix, keep only the highest-priority source
    for prefix, group in prefix_groups.items():
        group.sort(key=lambda r: priority.get(r.source, 99))
        for i, route in enumerate(group):
            route.active = i == 0

    # Check if more-specific UDRs override less-specific system routes
    user_routes = [
        r for r in routes
        if r.source == "User" and r.active
        and r.address_prefix != "(gateway learned)"
    ]
    for r in routes:
        if r.source != "User" and r.active:
            for udr in user_routes:
                if _prefix_contains(udr.address_prefix, r.address_prefix):
                    pass  # UDR is more specific, doesn't override broader
                elif _prefix_contains(r.address_prefix, udr.address_prefix):
                    pass  # System is broader, UDR overrides subset

    return routes


def _longest_prefix_match(
    routes: list[EffectiveRoute],
    dest_ip: str,
) -> EffectiveRoute | None:
    """Find the most specific matching route for a destination IP."""
    dest = ipaddress.ip_address(dest_ip)
    best_match: EffectiveRoute | None = None
    best_prefix_len = -1

    for route in routes:
        if route.address_prefix == "(gateway learned)":
            continue
        try:
            network = ipaddress.ip_network(route.address_prefix, strict=False)
        except ValueError:
            continue
        if dest in network and network.prefixlen > best_prefix_len:
            best_match = route
            best_prefix_len = network.prefixlen

    return best_match


def _prefix_contains(outer: str, inner: str) -> bool:
    """Check if outer prefix contains inner prefix."""
    try:
        outer_net = ipaddress.ip_network(outer, strict=False)
        inner_net = ipaddress.ip_network(inner, strict=False)
        return (
            inner_net.network_address >= outer_net.network_address
            and inner_net.broadcast_address <= outer_net.broadcast_address
        )
    except ValueError:
        return False
