"""DNS-focused report generation."""

from __future__ import annotations

from collections import defaultdict
from ipaddress import ip_address
from pathlib import Path

from netinspect.models.types import Topology


def generate_dns_report(topology: Topology) -> str:
    """Generate a DNS-focused Markdown report."""
    resolver_usage: dict[str, set[str]] = defaultdict(set)
    private_resolvers: set[str] = set()
    public_resolvers: set[str] = set()
    other_resolvers: set[str] = set()
    azure_default_vnets = 0

    for vnet in topology.vnets:
        if not vnet.dns_servers:
            azure_default_vnets += 1
            continue
        for resolver in vnet.dns_servers:
            resolver_usage[resolver].add(vnet.name)
            match _resolver_scope(resolver):
                case "private":
                    private_resolvers.add(resolver)
                case "public":
                    public_resolvers.add(resolver)
                case _:
                    other_resolvers.add(resolver)

    lines = [
        "# DNS Configuration Report",
        "",
        "This report summarizes VNet DNS settings, highlights configured private "
        "resolver IPs, and lists Private DNS zone links.",
        "",
        "## Summary",
        "",
        f"- **VNets:** {len(topology.vnets)}",
        f"- **VNets using Azure-provided DNS:** {azure_default_vnets}",
        f"- **VNets using custom DNS servers:** {len(topology.vnets) - azure_default_vnets}",
        f"- **Unique private resolver IPs:** {len(private_resolvers)}",
        f"- **Unique public resolver IPs:** {len(public_resolvers)}",
        f"- **Private DNS zones:** {len(topology.private_dns_zones)}",
    ]

    lines.extend(_vnet_dns_section(topology))
    lines.extend(_resolver_inventory_section(
        heading="## Private Resolver Inventory",
        resolvers=private_resolvers,
        resolver_usage=resolver_usage,
        empty_message="No private resolver IPs were identified in VNet DNS settings.",
    ))
    lines.extend(_resolver_inventory_section(
        heading="## Public Resolver Inventory",
        resolvers=public_resolvers,
        resolver_usage=resolver_usage,
        empty_message="No public resolver IPs were identified in VNet DNS settings.",
    ))

    if other_resolvers:
        lines.extend([
            "## Other DNS Endpoints",
            "",
            "| Endpoint | Used By VNets |",
            "|----------|----------------|",
        ])
        for resolver in sorted(other_resolvers):
            lines.append(f"| {resolver} | {', '.join(sorted(resolver_usage[resolver]))} |")
        lines.append("")

    lines.extend(_private_dns_zone_section(topology))
    return "\n".join(lines).rstrip() + "\n"


def export_dns_report(topology: Topology, output_path: Path) -> None:
    """Generate and write the DNS Markdown report."""
    output_path.write_text(generate_dns_report(topology), encoding="utf-8")


def _resolver_scope(value: str) -> str:
    try:
        return "private" if ip_address(value).is_private else "public"
    except ValueError:
        return "other"


def _vnet_dns_section(topology: Topology) -> list[str]:
    lines = [
        "",
        "## VNet DNS Configuration",
        "",
        "| VNet | DNS Mode | Configured Servers | Private Resolvers | Public Resolvers |",
        "|------|----------|--------------------|-------------------|------------------|",
    ]

    for vnet in topology.vnets:
        if not vnet.dns_servers:
            lines.append(f"| {vnet.name} | Azure Default | Azure-provided | — | — |")
            continue

        private = [
            resolver for resolver in vnet.dns_servers
            if _resolver_scope(resolver) == "private"
        ]
        public = [
            resolver for resolver in vnet.dns_servers
            if _resolver_scope(resolver) == "public"
        ]
        configured = ", ".join(f"`{resolver}`" for resolver in vnet.dns_servers)
        lines.append(
            f"| {vnet.name} | Custom | {configured} | "
            f"{', '.join(private) or '—'} | {', '.join(public) or '—'} |"
        )

    lines.append("")
    return lines


def _resolver_inventory_section(
    *,
    heading: str,
    resolvers: set[str],
    resolver_usage: dict[str, set[str]],
    empty_message: str,
) -> list[str]:
    lines = ["", heading, ""]
    if not resolvers:
        lines.extend([empty_message, ""])
        return lines

    lines.extend([
        "| Resolver | Used By VNets |",
        "|----------|----------------|",
    ])
    for resolver in sorted(resolvers):
        lines.append(f"| `{resolver}` | {', '.join(sorted(resolver_usage[resolver]))} |")
    lines.append("")
    return lines


def _private_dns_zone_section(topology: Topology) -> list[str]:
    lines = ["", "## Private DNS Zones", ""]
    if not topology.private_dns_zones:
        lines.extend(["No private DNS zones found.", ""])
        return lines

    for zone in topology.private_dns_zones:
        linked_vnets = ", ".join(sorted(link.vnet_name for link in zone.vnet_links)) or "None"
        lines.extend([
            f"### {zone.name}",
            "",
            f"- **Resource Group:** `{zone.resource_group}`",
            f"- **Record Sets:** {zone.record_count}",
            f"- **Linked VNets:** {linked_vnets}",
            "",
        ])

        if zone.vnet_links:
            lines.extend([
                "| VNet | Registration |",
                "|------|-------------|",
            ])
            for link in zone.vnet_links:
                registration = "Enabled" if link.registration_enabled else "Disabled"
                lines.append(f"| {link.vnet_name} | {registration} |")
            lines.append("")

    return lines
