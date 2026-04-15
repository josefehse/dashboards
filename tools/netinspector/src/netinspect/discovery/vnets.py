"""Discover VNets, subnets, and peerings."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import Peering, PeeringState, Subnet, VNet

console = Console()


def discover_vnets(
    network_client: NetworkManagementClient,
    resource_group: str | None = None,
    vnet_name: str | None = None,
) -> list[VNet]:
    """Discover VNets in the subscription.

    If resource_group and vnet_name are provided, start from that specific VNet
    and follow peerings to discover connected VNets.
    If only resource_group is provided, discover all VNets in that resource group.
    Otherwise, discover all VNets in the subscription.
    """
    if vnet_name and resource_group:
        return _discover_from_vnet(network_client, resource_group, vnet_name)

    vnets = []
    if resource_group:
        raw_vnets = network_client.virtual_networks.list(resource_group)
    else:
        raw_vnets = network_client.virtual_networks.list_all()

    for raw in raw_vnets:
        vnet = _parse_vnet(raw)
        vnets.append(vnet)
        console.print(f"  Discovered VNet: [cyan]{vnet.name}[/cyan] ({vnet.location})")

    return vnets


def _discover_from_vnet(
    network_client: NetworkManagementClient,
    resource_group: str,
    vnet_name: str,
) -> list[VNet]:
    """Start from a specific VNet and follow peerings to discover the topology."""
    discovered: dict[str, VNet] = {}
    to_visit: list[tuple[str, str]] = [(resource_group, vnet_name)]

    while to_visit:
        rg, name = to_visit.pop()
        vnet_key = f"{rg}/{name}".lower()
        if vnet_key in discovered:
            continue

        try:
            raw = network_client.virtual_networks.get(rg, name, expand="subnets")
        except Exception as e:
            console.print(f"  [yellow]Could not access VNet {name} in {rg}: {e}[/yellow]")
            continue

        vnet = _parse_vnet(raw)
        discovered[vnet_key] = vnet
        console.print(f"  Discovered VNet: [cyan]{vnet.name}[/cyan] ({vnet.location})")

        # Queue peered VNets for discovery
        for peering in vnet.peerings:
            remote_rg, remote_name = _parse_vnet_id(peering.remote_vnet_id)
            if remote_rg and remote_name:
                to_visit.append((remote_rg, remote_name))

    return list(discovered.values())


def _parse_vnet(raw) -> VNet:
    """Parse an Azure VNet SDK object into our VNet dataclass."""
    rg = _extract_resource_group(raw.id)

    subnets = []
    for s in raw.subnets or []:
        subnets.append(Subnet(
            id=s.id,
            name=s.name,
            address_prefix=(
                s.address_prefix or (s.address_prefixes[0] if s.address_prefixes else "")
            ),
            nsg_id=s.network_security_group.id if s.network_security_group else None,
            route_table_id=s.route_table.id if s.route_table else None,
            nat_gateway_id=s.nat_gateway.id if s.nat_gateway else None,
            delegations=[d.service_name for d in (s.delegations or [])],
            service_endpoints=[se.service for se in (s.service_endpoints or [])],
        ))

    peerings = []
    for p in raw.virtual_network_peerings or []:
        remote_id = p.remote_virtual_network.id if p.remote_virtual_network else ""
        remote_name = remote_id.split("/")[-1] if remote_id else ""
        peerings.append(Peering(
            id=p.id,
            name=p.name,
            remote_vnet_id=remote_id,
            remote_vnet_name=remote_name,
            state=PeeringState(p.peering_state) if p.peering_state else PeeringState.DISCONNECTED,
            allow_virtual_network_access=p.allow_virtual_network_access or False,
            allow_forwarded_traffic=p.allow_forwarded_traffic or False,
            allow_gateway_transit=p.allow_gateway_transit or False,
            use_remote_gateways=p.use_remote_gateways or False,
        ))

    return VNet(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        address_spaces=raw.address_space.address_prefixes if raw.address_space else [],
        dns_servers=(
            raw.dhcp_options.dns_servers
            if raw.dhcp_options and raw.dhcp_options.dns_servers
            else []
        ),
        subnets=subnets,
        peerings=peerings,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an Azure resource ID."""
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


def _parse_vnet_id(vnet_id: str) -> tuple[str | None, str | None]:
    """Extract resource group and VNet name from a VNet resource ID."""
    parts = vnet_id.split("/")
    try:
        rg_idx = [p.lower() for p in parts].index("resourcegroups")
        name_idx = [p.lower() for p in parts].index("virtualnetworks")
        return parts[rg_idx + 1], parts[name_idx + 1]
    except (ValueError, IndexError):
        return None, None
