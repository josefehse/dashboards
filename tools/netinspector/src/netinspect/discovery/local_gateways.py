"""Discover Local Network Gateways (on-premises endpoints)."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import LocalNetworkGateway

console = Console()


def discover_local_network_gateways(
    network_client: NetworkManagementClient,
) -> list[LocalNetworkGateway]:
    """Discover all Local Network Gateways in the subscription.

    Local Network Gateways must be listed per resource group.
    """
    gateways = []
    seen_rgs: set[str] = set()

    for vnet in network_client.virtual_networks.list_all():
        rg = _extract_resource_group(vnet.id)
        if rg.lower() in seen_rgs:
            continue
        seen_rgs.add(rg.lower())

        try:
            for raw in network_client.local_network_gateways.list(rg):
                gw = _parse_local_gateway(raw)
                gateways.append(gw)

                prefixes = len(gw.address_prefixes)
                bgp = f"BGP ASN {gw.bgp_asn}" if gw.bgp_asn else "no BGP"
                console.print(
                    f"  Discovered Local GW: [cyan]{gw.name}[/cyan] "
                    f"({gw.gateway_ip or 'no IP'}, "
                    f"{prefixes} prefixes, {bgp})"
                )
        except Exception as e:
            console.print(
                f"  [yellow]Could not list local gateways in {rg}: "
                f"{e}[/yellow]"
            )

    if not gateways:
        console.print("  [dim]No local network gateways found.[/dim]")

    return gateways


def _parse_local_gateway(raw) -> LocalNetworkGateway:
    """Parse a Local Network Gateway SDK object."""
    rg = _extract_resource_group(raw.id)

    prefixes = []
    if raw.local_network_address_space:
        prefixes = list(
            raw.local_network_address_space.address_prefixes or []
        )

    bgp_asn = None
    bgp_addr = None
    if raw.bgp_settings:
        bgp_asn = raw.bgp_settings.asn
        bgp_addr = raw.bgp_settings.bgp_peering_address

    return LocalNetworkGateway(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        gateway_ip=raw.gateway_ip_address,
        address_prefixes=prefixes,
        bgp_asn=bgp_asn,
        bgp_peering_address=bgp_addr,
        fqdn=getattr(raw, "fqdn", None),
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
