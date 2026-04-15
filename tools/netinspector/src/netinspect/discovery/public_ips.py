"""Discover Public IP addresses and their resource associations."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import PublicIP

console = Console()


def discover_public_ips(
    network_client: NetworkManagementClient,
) -> list[PublicIP]:
    """Discover all Public IP addresses in the subscription."""
    pips = []

    for raw in network_client.public_ip_addresses.list_all():
        pip = _parse_public_ip(raw)
        pips.append(pip)

        assoc = pip.associated_resource_type or "unassociated"
        ip_display = pip.ip_address or "(not allocated)"
        console.print(
            f"  Discovered PIP: [cyan]{pip.name}[/cyan] "
            f"({ip_display}, {pip.sku}, {assoc})"
        )

    return pips


def _parse_public_ip(raw) -> PublicIP:
    """Parse an Azure Public IP SDK object."""
    rg = _extract_resource_group(raw.id)

    # Determine associated resource
    assoc_id = None
    assoc_type = None
    if raw.ip_configuration:
        assoc_id = raw.ip_configuration.id
        assoc_type = _classify_resource(assoc_id)
    elif raw.nat_gateway:
        assoc_id = raw.nat_gateway.id
        assoc_type = "NAT Gateway"

    dns_fqdn = None
    if raw.dns_settings and raw.dns_settings.fqdn:
        dns_fqdn = raw.dns_settings.fqdn

    return PublicIP(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        ip_address=raw.ip_address,
        allocation_method=raw.public_ip_allocation_method or "Static",
        sku=raw.sku.name if raw.sku else "Basic",
        associated_resource_id=assoc_id,
        associated_resource_type=assoc_type,
        dns_fqdn=dns_fqdn,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _classify_resource(resource_id: str) -> str:
    """Classify the type of resource a PIP is associated with."""
    rid = resource_id.lower()
    if "/networkinterfaces/" in rid:
        return "NIC"
    if "/loadbalancers/" in rid:
        return "Load Balancer"
    if "/virtualnetworkgateways/" in rid:
        return "VPN Gateway"
    if "/bastionhosts/" in rid:
        return "Bastion"
    if "/azurefirewalls/" in rid:
        return "Azure Firewall"
    if "/applicationgateways/" in rid:
        return "App Gateway"
    return "Other"


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
