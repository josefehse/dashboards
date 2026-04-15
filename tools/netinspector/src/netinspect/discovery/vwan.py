"""Discover Virtual WAN, Virtual Hubs, and hub connections."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import (
    HubRouteTable,
    HubVnetConnection,
    VirtualHub,
    VirtualWan,
)

console = Console()


def discover_virtual_wans(
    network_client: NetworkManagementClient,
) -> tuple[list[VirtualWan], list[VirtualHub]]:
    """Discover all Virtual WANs and their hubs."""
    wans: list[VirtualWan] = []
    hubs: list[VirtualHub] = []

    # Discover Virtual WANs
    try:
        for raw in network_client.virtual_wans.list():
            wan = _parse_wan(raw)
            wans.append(wan)
            console.print(
                f"  Discovered vWAN: [cyan]{wan.name}[/cyan] "
                f"({wan.wan_type}, {len(wan.hub_ids)} hubs, "
                f"b2b={'✅' if wan.allow_branch_to_branch else '❌'})"
            )
    except Exception as e:
        console.print(
            f"  [yellow]Could not list Virtual WANs: {e}[/yellow]"
        )

    # Discover Virtual Hubs
    try:
        for raw in network_client.virtual_hubs.list():
            hub = _parse_hub(raw)

            # Discover hub VNet connections
            hub.vnet_connections = _discover_hub_vnet_connections(
                network_client, hub.resource_group, hub.name,
            )

            # Discover hub route tables
            hub.route_tables = _discover_hub_route_tables(
                network_client, hub.resource_group, hub.name,
            )

            hubs.append(hub)

            conn_count = len(hub.vnet_connections)
            rt_count = len(hub.route_tables)
            console.print(
                f"  Discovered Hub: [cyan]{hub.name}[/cyan] "
                f"({hub.address_prefix or '?'}, "
                f"{conn_count} VNet conns, {rt_count} route tables, "
                f"routing: {hub.routing_state})"
            )
    except Exception as e:
        console.print(
            f"  [yellow]Could not list Virtual Hubs: {e}[/yellow]"
        )

    if not wans and not hubs:
        console.print("  [dim]No Virtual WAN resources found.[/dim]")

    return wans, hubs


def _discover_hub_vnet_connections(
    network_client: NetworkManagementClient,
    resource_group: str,
    hub_name: str,
) -> list[HubVnetConnection]:
    """Discover VNet connections for a Virtual Hub."""
    connections = []
    try:
        for raw in network_client.hub_virtual_network_connections.list(
            resource_group, hub_name,
        ):
            vnet_id = ""
            vnet_name = ""
            if raw.remote_virtual_network:
                vnet_id = raw.remote_virtual_network.id or ""
                vnet_name = vnet_id.split("/")[-1] if vnet_id else ""

            routing = raw.routing_configuration
            allow_hub = True
            allow_remote = True
            internet_sec = False
            if hasattr(raw, "allow_hub_to_remote_vnet_transit"):
                allow_hub = raw.allow_hub_to_remote_vnet_transit or True
            if hasattr(raw, "allow_remote_vnet_to_use_hub_vnet_gateways"):
                allow_remote = (
                    raw.allow_remote_vnet_to_use_hub_vnet_gateways or True
                )
            if hasattr(raw, "enable_internet_security"):
                internet_sec = raw.enable_internet_security or False

            # Try newer property names
            if routing:
                pass  # Routing config is available but complex

            connections.append(HubVnetConnection(
                id=raw.id or "",
                name=raw.name or "",
                remote_vnet_id=vnet_id,
                remote_vnet_name=vnet_name,
                allow_hub_to_remote=allow_hub,
                allow_remote_to_hub=allow_remote,
                enable_internet_security=internet_sec,
                provisioning_state=raw.provisioning_state or "",
            ))
    except Exception as e:
        console.print(
            f"  [yellow]Could not list hub connections for "
            f"{hub_name}: {e}[/yellow]"
        )

    return connections


def _discover_hub_route_tables(
    network_client: NetworkManagementClient,
    resource_group: str,
    hub_name: str,
) -> list[HubRouteTable]:
    """Discover route tables for a Virtual Hub."""
    route_tables = []
    try:
        for raw in network_client.hub_route_tables.list(
            resource_group, hub_name,
        ):
            routes = []
            for r in raw.routes or []:
                routes.append({
                    "name": r.name or "",
                    "destination_type": r.destination_type or "",
                    "destinations": ", ".join(r.destinations or []),
                    "next_hop_type": r.next_hop_type or "",
                    "next_hop": r.next_hop or "",
                })

            # Extract associated/propagating connection labels
            associated = []
            if raw.associated_connections:
                associated = [
                    c.split("/")[-1] if "/" in c else c
                    for c in raw.associated_connections
                ]
            propagating = []
            if raw.propagating_connections:
                propagating = [
                    c.split("/")[-1] if "/" in c else c
                    for c in raw.propagating_connections
                ]

            route_tables.append(HubRouteTable(
                id=raw.id or "",
                name=raw.name or "",
                routes=routes,
                associated_connections=associated,
                propagating_connections=propagating,
                provisioning_state=raw.provisioning_state or "",
            ))
    except Exception as e:
        console.print(
            f"  [yellow]Could not list hub route tables for "
            f"{hub_name}: {e}[/yellow]"
        )

    return route_tables


def _parse_wan(raw) -> VirtualWan:
    """Parse a Virtual WAN SDK object."""
    rg = _extract_resource_group(raw.id)

    hub_ids = []
    if raw.virtual_hubs:
        hub_ids = [h.id for h in raw.virtual_hubs if h.id]

    return VirtualWan(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        wan_type=raw.type_properties_type or "Standard",
        disable_vpn_encryption=raw.disable_vpn_encryption or False,
        allow_branch_to_branch=raw.allow_branch_to_branch_traffic
        if raw.allow_branch_to_branch_traffic is not None else True,
        allow_vnet_to_vnet=raw.allow_vnet_to_vnet_traffic
        if raw.allow_vnet_to_vnet_traffic is not None else True,
        hub_ids=hub_ids,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _parse_hub(raw) -> VirtualHub:
    """Parse a Virtual Hub SDK object."""
    rg = _extract_resource_group(raw.id)

    return VirtualHub(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        virtual_wan_id=raw.virtual_wan.id if raw.virtual_wan else None,
        address_prefix=raw.address_prefix,
        sku=raw.sku,
        provisioning_state=raw.provisioning_state or "",
        routing_state=raw.routing_state or "",
        vpn_gateway_id=(
            raw.vpn_gateway.id if raw.vpn_gateway else None
        ),
        er_gateway_id=(
            raw.express_route_gateway.id
            if raw.express_route_gateway else None
        ),
        p2s_gateway_id=(
            raw.p2_s_vpn_gateway.id
            if raw.p2_s_vpn_gateway else None
        ),
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
