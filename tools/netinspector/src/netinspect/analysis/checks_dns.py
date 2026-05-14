"""DNS-specific analysis checks for Azure networking best practices."""

from __future__ import annotations

from ipaddress import ip_address

from netinspect.analysis.findings import (
    AnalysisReport,
    Category,
    Finding,
    Severity,
)
from netinspect.models.types import Topology

CAT = Category.DESIGN


def check_dns(topology: Topology, report: AnalysisReport) -> None:
    """Run all DNS-focused analysis checks."""
    _check_peered_dns_mismatch(topology, report)
    _check_public_dns_resolvers(topology, report)
    _check_mixed_public_private_dns(topology, report)
    _check_single_dns_server(topology, report)
    _check_orphaned_dns_zones(topology, report)
    _check_vnets_without_zone_links(topology, report)
    _check_privatelink_zones_missing_hub(topology, report)
    _check_auto_registration_on_privatelink(topology, report)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _resolver_scope(value: str) -> str:
    try:
        return "private" if ip_address(value).is_private else "public"
    except ValueError:
        return "other"


def _check_peered_dns_mismatch(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Peered VNets should share the same DNS configuration."""
    vnet_map = {v.name: v for v in topology.vnets}
    checked: set[tuple[str, str]] = set()
    mismatched: list[tuple[str, str]] = []

    for vnet in topology.vnets:
        vdns = tuple(sorted(vnet.dns_servers))
        for p in vnet.peerings:
            pair = tuple(sorted([vnet.name, p.remote_vnet_name]))
            if pair in checked:
                continue
            checked.add(pair)
            remote = vnet_map.get(p.remote_vnet_name)
            if not remote:
                continue
            rdns = tuple(sorted(remote.dns_servers))
            if vdns != rdns:
                mismatched.append(pair)

    if mismatched:
        sample = "; ".join(
            f"{a} \u2194 {b}" for a, b in mismatched[:5]
        )
        extra = f" (and {len(mismatched) - 5} more)" if len(mismatched) > 5 else ""
        report.add(Finding(
            severity=Severity.WARNING,
            category=CAT,
            title=f"DNS mismatch across {len(mismatched)} peered VNet pairs",
            description=(
                f"{len(mismatched)} peered VNet pairs use different DNS "
                f"server configurations. Workloads that rely on peering "
                f"for connectivity may fail to resolve names consistently. "
                f"Examples: {sample}{extra}."
            ),
            recommendation=(
                "Align DNS settings across peered VNets, or ensure "
                "that each VNet's DNS servers can resolve the same "
                "set of private zones (e.g. via conditional forwarding)."
            ),
            waf_pillar="RE:05",
        ))


def _check_public_dns_resolvers(
    topology: Topology, report: AnalysisReport,
) -> None:
    """VNets using public DNS resolvers cannot resolve Private Link endpoints."""
    affected: list[tuple[str, list[str]]] = []
    for vnet in topology.vnets:
        pub = [s for s in vnet.dns_servers if _resolver_scope(s) == "public"]
        if pub:
            affected.append((vnet.name, pub))

    if not affected:
        return

    names = ", ".join(n for n, _ in affected[:6])
    extra = f" (and {len(affected) - 6} more)" if len(affected) > 6 else ""
    report.add(Finding(
        severity=Severity.WARNING,
        category=CAT,
        title=f"{len(affected)} VNet(s) use public DNS resolvers",
        description=(
            f"VNets configured with public DNS servers cannot resolve "
            f"Azure Private Link endpoints. Affected: {names}{extra}."
        ),
        recommendation=(
            "Replace public DNS servers with Azure Private Resolver "
            "or on-premises forwarders that conditionally forward "
            "privatelink.* zones to Azure DNS (168.63.129.16)."
        ),
        waf_pillar="SE:06",
    ))


def _check_mixed_public_private_dns(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Mixing public and private DNS on the same VNet is unpredictable."""
    for vnet in topology.vnets:
        if len(vnet.dns_servers) < 2:
            continue
        scopes = {_resolver_scope(s) for s in vnet.dns_servers}
        if "public" in scopes and "private" in scopes:
            servers = ", ".join(vnet.dns_servers)
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title=f"Mixed public and private DNS on '{vnet.name}'",
                description=(
                    f"VNet '{vnet.name}' uses both public and private "
                    f"DNS servers ({servers}). Azure resolves against "
                    f"each server in order; mixing scopes leads to "
                    f"inconsistent name resolution."
                ),
                recommendation=(
                    "Use only private DNS forwarders and configure "
                    "conditional forwarding for external zones."
                ),
                resource_name=vnet.name,
                resource_id=vnet.id,
            ))


def _check_single_dns_server(
    topology: Topology, report: AnalysisReport,
) -> None:
    """A single custom DNS server is a single point of failure."""
    affected = [
        v.name for v in topology.vnets
        if len(v.dns_servers) == 1
    ]
    if not affected:
        return

    names = ", ".join(affected[:6])
    extra = f" (and {len(affected) - 6} more)" if len(affected) > 6 else ""
    report.add(Finding(
        severity=Severity.INFO,
        category=CAT,
        title=f"{len(affected)} VNet(s) have a single DNS server",
        description=(
            f"VNets with only one custom DNS server have no DNS "
            f"redundancy. If the server becomes unavailable, all "
            f"name resolution fails. Affected: {names}{extra}."
        ),
        recommendation=(
            "Configure at least two DNS servers per VNet for "
            "high availability."
        ),
        resource_name=", ".join(affected),
        waf_pillar="RE:05",
    ))


def _check_orphaned_dns_zones(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Private DNS zones with no VNet links are unreachable."""
    orphaned = [
        z.name for z in topology.private_dns_zones
        if not z.vnet_links
    ]
    if not orphaned:
        return

    zones = ", ".join(orphaned[:6])
    extra = f" (and {len(orphaned) - 6} more)" if len(orphaned) > 6 else ""
    report.add(Finding(
        severity=Severity.WARNING,
        category=CAT,
        title=f"{len(orphaned)} private DNS zone(s) have no VNet links",
        description=(
            f"Zones without VNet links are unreachable — no VNet can "
            f"resolve records in them. Zones: {zones}{extra}."
        ),
        recommendation=(
            "Link each zone to the VNets that need to resolve its "
            "records, or delete unused zones."
        ),
    ))


def _check_vnets_without_zone_links(
    topology: Topology, report: AnalysisReport,
) -> None:
    """VNets using Azure DNS but not linked to any private zone miss PL resolution."""
    if not topology.private_dns_zones:
        return

    zone_linked: set[str] = set()
    for z in topology.private_dns_zones:
        for link in z.vnet_links:
            zone_linked.add(link.vnet_name)

    # Azure-DNS VNets missing zone links are more impactful
    azure_dns_unlinked = [
        v.name for v in topology.vnets
        if not v.dns_servers and v.name not in zone_linked
    ]
    if azure_dns_unlinked:
        names = ", ".join(azure_dns_unlinked[:6])
        extra = (
            f" (and {len(azure_dns_unlinked) - 6} more)"
            if len(azure_dns_unlinked) > 6
            else ""
        )
        report.add(Finding(
            severity=Severity.WARNING,
            category=CAT,
            title=(
                f"{len(azure_dns_unlinked)} Azure-DNS VNet(s) not "
                f"linked to any private DNS zone"
            ),
            description=(
                f"VNets using Azure-provided DNS that are not linked "
                f"to private DNS zones cannot resolve Private Link "
                f"endpoints. Affected: {names}{extra}."
            ),
            recommendation=(
                "Link these VNets to the relevant privatelink.* "
                "zones so Azure DNS can resolve private endpoints."
            ),
            waf_pillar="SE:06",
        ))


def _check_privatelink_zones_missing_hub(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Privatelink zones should be linked to hub/firewall VNets for central resolution."""
    if len(topology.vnets) < 3:
        return

    # Identify hub VNets (most peerings, at least 5)
    max_peerings = max((len(v.peerings) for v in topology.vnets), default=0)
    if max_peerings < 5:
        return

    threshold = max(5, max_peerings // 2)
    hubs = {v.name for v in topology.vnets if len(v.peerings) >= threshold}
    if not hubs:
        return

    pl_zones_missing: list[tuple[str, set[str]]] = []
    for zone in topology.private_dns_zones:
        if "privatelink" not in zone.name:
            continue
        linked = {link.vnet_name for link in zone.vnet_links}
        missing = hubs - linked
        if missing:
            pl_zones_missing.append((zone.name, missing))

    if not pl_zones_missing:
        return

    zones_str = ", ".join(z for z, _ in pl_zones_missing[:5])
    extra = (
        f" (and {len(pl_zones_missing) - 5} more)"
        if len(pl_zones_missing) > 5
        else ""
    )
    hub_str = ", ".join(sorted(hubs))
    report.add(Finding(
        severity=Severity.WARNING,
        category=CAT,
        title=(
            f"{len(pl_zones_missing)} privatelink zone(s) not linked "
            f"to hub VNet(s)"
        ),
        description=(
            f"Hub VNets ({hub_str}) typically forward DNS for "
            f"spoke VNets. If a privatelink zone is not linked to "
            f"the hub, conditional forwarding to 168.63.129.16 "
            f"won't resolve those records. "
            f"Zones: {zones_str}{extra}."
        ),
        recommendation=(
            "Link all privatelink.* zones to hub/firewall VNets "
            "that serve as DNS forwarders."
        ),
        waf_pillar="SE:06",
    ))


def _check_auto_registration_on_privatelink(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Auto-registration on privatelink zones can create conflicting records."""
    for zone in topology.private_dns_zones:
        if "privatelink" not in zone.name:
            continue
        reg_vnets = [
            link.vnet_name for link in zone.vnet_links
            if link.registration_enabled
        ]
        if reg_vnets:
            vnets_str = ", ".join(reg_vnets[:5])
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title=(
                    f"Auto-registration enabled on privatelink zone "
                    f"'{zone.name}'"
                ),
                description=(
                    f"VNet(s) {vnets_str} have auto-registration "
                    f"enabled for '{zone.name}'. Privatelink zones "
                    f"are managed by the platform; auto-registration "
                    f"can create conflicting A records."
                ),
                recommendation=(
                    "Disable auto-registration on privatelink zones. "
                    "Use a separate zone for VM name registration."
                ),
                resource_name=zone.name,
                resource_id=zone.id,
            ))
