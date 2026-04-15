"""Discover Network Security Groups and security rules."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import NSG, SecurityRule, SecurityRuleAccess, SecurityRuleDirection

console = Console()


def discover_nsgs(network_client: NetworkManagementClient) -> list[NSG]:
    """Discover all NSGs in the subscription."""
    nsgs = []

    for raw in network_client.network_security_groups.list_all():
        nsg = _parse_nsg(raw)
        nsgs.append(nsg)
        console.print(
            f"  Discovered NSG: [cyan]{nsg.name}[/cyan] "
            f"({len(nsg.rules)} rules, "
            f"{len(nsg.associated_subnets)} subnets, "
            f"{len(nsg.associated_nics)} NICs)"
        )

    return nsgs


def _parse_nsg(raw) -> NSG:
    """Parse an Azure NSG SDK object into our NSG dataclass."""
    rg = _extract_resource_group(raw.id)

    rules = []
    # Include both custom and default rules for completeness
    all_rules = list(raw.security_rules or []) + list(raw.default_security_rules or [])
    for r in all_rules:
        rules.append(SecurityRule(
            name=r.name,
            priority=r.priority,
            direction=SecurityRuleDirection(r.direction),
            access=SecurityRuleAccess(r.access),
            protocol=r.protocol or "*",
            source_address_prefix=r.source_address_prefix,
            source_address_prefixes=list(r.source_address_prefixes or []),
            source_port_range=r.source_port_range,
            destination_address_prefix=r.destination_address_prefix,
            destination_address_prefixes=list(r.destination_address_prefixes or []),
            destination_port_range=r.destination_port_range,
            description=r.description,
        ))

    # Sort by direction then priority
    rules.sort(key=lambda r: (r.direction.value, r.priority))

    associated_subnets = [s.id for s in (raw.subnets or [])]
    associated_nics = [n.id for n in (raw.network_interfaces or [])]

    return NSG(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        rules=rules,
        associated_subnets=associated_subnets,
        associated_nics=associated_nics,
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
