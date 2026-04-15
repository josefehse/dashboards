"""Discover route tables and user-defined routes."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import Route, RouteTable

console = Console()


def discover_route_tables(network_client: NetworkManagementClient) -> list[RouteTable]:
    """Discover all route tables in the subscription."""
    route_tables = []

    for raw in network_client.route_tables.list_all():
        rt = _parse_route_table(raw)
        route_tables.append(rt)
        console.print(
            f"  Discovered Route Table: [cyan]{rt.name}[/cyan] "
            f"({len(rt.routes)} routes, {len(rt.associated_subnets)} subnets)"
        )

    return route_tables


def _parse_route_table(raw) -> RouteTable:
    """Parse an Azure route table SDK object into our RouteTable dataclass."""
    rg = _extract_resource_group(raw.id)

    routes = []
    for r in raw.routes or []:
        routes.append(Route(
            name=r.name,
            address_prefix=r.address_prefix or "",
            next_hop_type=r.next_hop_type or "",
            next_hop_ip=r.next_hop_ip_address,
        ))

    associated_subnets = []
    for s in raw.subnets or []:
        associated_subnets.append(s.id)

    return RouteTable(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        routes=routes,
        associated_subnets=associated_subnets,
        disable_bgp_route_propagation=raw.disable_bgp_route_propagation or False,
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
