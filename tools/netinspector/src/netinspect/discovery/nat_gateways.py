"""Discover NAT Gateways."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import NatGateway

console = Console()


def discover_nat_gateways(
    network_client: NetworkManagementClient,
) -> list[NatGateway]:
    """Discover all NAT Gateways in the subscription."""
    nat_gateways = []

    for raw in network_client.nat_gateways.list_all():
        ng = _parse_nat_gateway(raw)
        nat_gateways.append(ng)
        console.print(
            f"  Discovered NAT Gateway: [cyan]{ng.name}[/cyan] "
            f"({len(ng.public_ip_addresses)} PIPs, "
            f"{len(ng.associated_subnets)} subnets)"
        )

    return nat_gateways


def _parse_nat_gateway(raw) -> NatGateway:
    """Parse an Azure NAT Gateway SDK object."""
    rg = _extract_resource_group(raw.id)

    public_ips = []
    for pip in raw.public_ip_addresses or []:
        public_ips.append(pip.id)

    public_prefixes = []
    for prefix in raw.public_ip_prefixes or []:
        public_prefixes.append(prefix.id)

    associated_subnets = []
    for s in raw.subnets or []:
        associated_subnets.append(s.id)

    return NatGateway(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        sku=raw.sku.name if raw.sku else "Standard",
        idle_timeout_minutes=raw.idle_timeout_in_minutes or 4,
        public_ip_addresses=public_ips,
        public_ip_prefixes=public_prefixes,
        associated_subnets=associated_subnets,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
