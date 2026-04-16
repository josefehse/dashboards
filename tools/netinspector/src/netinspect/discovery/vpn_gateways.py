"""Discover VPN Gateways and their connections."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import VpnGateway, VpnGatewayConnection

console = Console()


def discover_vpn_gateways(
    network_client: NetworkManagementClient,
) -> list[VpnGateway]:
    """Discover all Virtual Network Gateways in the subscription."""
    gateways = []

    # VPN Gateways must be listed per resource group
    seen_rgs: set[str] = set()
    for vnet in network_client.virtual_networks.list_all():
        rg = _extract_resource_group(vnet.id)
        if rg.lower() in seen_rgs:
            continue
        seen_rgs.add(rg.lower())

        try:
            for raw in network_client.virtual_network_gateways.list(rg):
                gw = _parse_gateway(raw)
                gw.connections = _discover_connections(
                    network_client, gw.resource_group, gw.name
                )
                gateways.append(gw)

                conn_info = f"{len(gw.connections)} connections"
                bgp_info = (
                    f"BGP ASN {gw.bgp_asn}" if gw.bgp_enabled else "no BGP"
                )
                console.print(
                    f"  Discovered Gateway: [cyan]{gw.name}[/cyan] "
                    f"({gw.gateway_type}, {gw.sku}, {bgp_info}, {conn_info})"
                )
        except Exception as e:
            console.print(
                f"  [yellow]Could not list gateways in {rg}: {e}[/yellow]"
            )

    return gateways


def _discover_connections(
    network_client: NetworkManagementClient,
    resource_group: str,
    gateway_name: str,
) -> list[VpnGatewayConnection]:
    """Discover connections for a specific gateway."""
    connections = []
    try:
        for raw in network_client.virtual_network_gateway_connections.list(
            resource_group
        ):
            # Filter connections that belong to this gateway
            gw1_id = (
                raw.virtual_network_gateway1.id
                if raw.virtual_network_gateway1 else ""
            )
            if gateway_name.lower() not in gw1_id.lower():
                continue

            # Get the individual connection for full status
            try:
                detail = network_client.virtual_network_gateway_connections.get(
                    resource_group, raw.name,
                )
                status = detail.connection_status or "Unknown"
            except Exception:
                status = raw.connection_status or "Unknown"

            remote_gw_id = None
            if raw.virtual_network_gateway2:
                remote_gw_id = raw.virtual_network_gateway2.id
            elif raw.local_network_gateway2:
                remote_gw_id = raw.local_network_gateway2.id
            elif raw.peer:
                # ExpressRoute connections reference the circuit via 'peer'
                remote_gw_id = raw.peer.id if hasattr(raw.peer, "id") else str(raw.peer)

            connections.append(VpnGatewayConnection(
                id=raw.id,
                name=raw.name,
                connection_type=raw.connection_type or "",
                status=status,
                remote_gateway_id=remote_gw_id,
                shared_key_set=bool(raw.shared_key),
                enable_bgp=raw.enable_bgp or False,
                routing_weight=raw.routing_weight or 0,
                express_route_gateway_bypass=getattr(
                    raw, "express_route_gateway_bypass", False
                ) or False,
            ))
    except Exception as e:
        console.print(
            f"  [yellow]Could not list connections for "
            f"{gateway_name}: {e}[/yellow]"
        )

    return connections


def _parse_gateway(raw) -> VpnGateway:
    """Parse a Virtual Network Gateway SDK object."""
    rg = _extract_resource_group(raw.id)

    # Extract VNet ID from IP configurations
    vnet_id = None
    public_ips = []
    for ip_config in raw.ip_configurations or []:
        if ip_config.subnet and ip_config.subnet.id:
            # Subnet ID format: .../virtualNetworks/<name>/subnets/...
            parts = ip_config.subnet.id.split("/subnets/")[0]
            vnet_id = parts
        if ip_config.public_ip_address:
            public_ips.append(ip_config.public_ip_address.id)

    bgp_asn = None
    bgp_addr = None
    bgp_enabled = raw.enable_bgp or False
    if raw.bgp_settings:
        bgp_asn = raw.bgp_settings.asn
        bgp_addr = raw.bgp_settings.bgp_peering_address

    return VpnGateway(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        gateway_type=raw.gateway_type or "",
        vpn_type=raw.vpn_type,
        sku=raw.sku.name if raw.sku else None,
        vnet_id=vnet_id,
        bgp_enabled=bgp_enabled,
        bgp_asn=bgp_asn,
        bgp_peering_address=bgp_addr,
        active_active=getattr(raw, "active", False) or False,
        public_ips=public_ips,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
