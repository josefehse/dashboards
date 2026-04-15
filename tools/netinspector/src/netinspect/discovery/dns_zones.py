"""Discover Private DNS Zones and their VNet links."""

from __future__ import annotations

from rich.console import Console

from netinspect.models.types import PrivateDnsVnetLink, PrivateDnsZone

console = Console()


def discover_private_dns_zones(credential, subscription_id: str) -> list[PrivateDnsZone]:
    """Discover all Private DNS Zones in the subscription.

    Uses azure-mgmt-privatedns (separate from azure-mgmt-network).
    Falls back gracefully if the package is not installed.
    """
    try:
        from azure.mgmt.privatedns import PrivateDnsManagementClient
    except ImportError:
        console.print(
            "  [yellow]azure-mgmt-privatedns not installed — "
            "skipping Private DNS zone discovery. "
            "Install with: pip install azure-mgmt-privatedns[/yellow]"
        )
        return []

    client = PrivateDnsManagementClient(credential, subscription_id)
    zones = []

    for raw_zone in client.private_zones.list():
        rg = _extract_resource_group(raw_zone.id)
        zone_name = raw_zone.name

        # Discover VNet links for this zone
        vnet_links = []
        try:
            for raw_link in client.virtual_network_links.list(rg, zone_name):
                vnet_id = (
                    raw_link.virtual_network.id
                    if raw_link.virtual_network else ""
                )
                vnet_name = vnet_id.split("/")[-1] if vnet_id else ""
                vnet_links.append(PrivateDnsVnetLink(
                    id=raw_link.id,
                    name=raw_link.name,
                    vnet_id=vnet_id,
                    vnet_name=vnet_name,
                    registration_enabled=(
                        raw_link.registration_enabled or False
                    ),
                ))
        except Exception as e:
            console.print(
                f"  [yellow]Could not list VNet links for "
                f"{zone_name}: {e}[/yellow]"
            )

        record_count = 0
        if hasattr(raw_zone, "number_of_record_sets"):
            record_count = raw_zone.number_of_record_sets or 0

        zone = PrivateDnsZone(
            id=raw_zone.id,
            name=zone_name,
            resource_group=rg,
            record_count=record_count,
            vnet_links=vnet_links,
            tags=dict(raw_zone.tags) if raw_zone.tags else {},
        )
        zones.append(zone)

        link_names = [lnk.vnet_name for lnk in vnet_links]
        console.print(
            f"  Discovered DNS Zone: [cyan]{zone_name}[/cyan] "
            f"({record_count} records, "
            f"linked to: {', '.join(link_names) or 'none'})"
        )

    return zones


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
