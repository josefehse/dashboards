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

    # Step 1: Use list_connections on the gateway itself to reliably get
    # all connection IDs — this works even when the connection resource
    # lives in a different resource group.
    conn_refs: list[tuple[str, str]] = []  # (rg, name) pairs
    try:
        for entry in network_client.virtual_network_gateways.list_connections(
            resource_group, gateway_name,
        ):
            conn_id = entry.id if hasattr(entry, "id") else ""
            if conn_id:
                conn_rg = _extract_resource_group(conn_id)
                conn_name = conn_id.split("/")[-1]
                conn_refs.append((conn_rg, conn_name))
    except Exception as e:
        console.print(
            f"  [yellow]Could not list_connections for "
            f"{gateway_name}: {e}[/yellow]"
        )

    # Fall back to listing connections in the gateway's RG if
    # list_connections returned nothing (older SDK versions).
    if not conn_refs:
        try:
            for raw in network_client.virtual_network_gateway_connections.list(
                resource_group,
            ):
                gw1_id = (
                    raw.virtual_network_gateway1.id
                    if raw.virtual_network_gateway1 else ""
                )
                if gateway_name.lower() in gw1_id.lower():
                    conn_refs.append((resource_group, raw.name))
        except Exception:
            pass

    # Step 2: GET full details for each connection
    for conn_rg, conn_name in conn_refs:
        try:
            detail = network_client.virtual_network_gateway_connections.get(
                conn_rg, conn_name,
            )
        except Exception as e:
            console.print(
                f"  [yellow]Could not get connection {conn_name}: {e}[/yellow]"
            )
            continue

        # Status: prefer connection_status, fall back to provisioning_state
        status = (
            getattr(detail, "connection_status", None)
            or getattr(detail, "provisioning_state", None)
            or "Unknown"
        )

        remote_gw_id = None
        if detail.virtual_network_gateway2:
            remote_gw_id = detail.virtual_network_gateway2.id
        elif detail.local_network_gateway2:
            remote_gw_id = detail.local_network_gateway2.id
        # ExpressRoute connections reference the ER circuit via 'peer'
        peer = getattr(detail, "peer", None)
        if not remote_gw_id and peer:
            remote_gw_id = peer.id if hasattr(peer, "id") else str(peer)

        connections.append(VpnGatewayConnection(
            id=detail.id,
            name=detail.name,
            connection_type=detail.connection_type or "",
            status=status,
            remote_gateway_id=remote_gw_id,
            shared_key_set=bool(detail.shared_key) if hasattr(detail, "shared_key") else False,
            enable_bgp=detail.enable_bgp or False,
            routing_weight=detail.routing_weight or 0,
            express_route_gateway_bypass=getattr(
                detail, "express_route_gateway_bypass", False
            ) or False,
        ))

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
