"""HTML report generation."""

from __future__ import annotations

from html import escape
from ipaddress import ip_address

from netinspect.export.mermaid import generate_mermaid_diagrams
from netinspect.models.types import Topology


def generate_topology_html(topology: Topology, *, include_analysis: bool = False) -> str:
    """Generate a static HTML topology report."""
    sections = [
        _summary_cards(
            "Topology summary",
            [
                (
                    "Subscriptions",
                    str(len(topology.subscription_ids or [topology.subscription_id])),
                ),
                ("VNets", str(len(topology.vnets))),
                ("Route Tables", str(len(topology.route_tables))),
                ("NSGs", str(len(topology.nsgs))),
                ("NAT Gateways", str(len(topology.nat_gateways))),
                ("VPN Gateways", str(len(topology.vpn_gateways))),
                ("Public IPs", str(len(topology.public_ips))),
                ("Private DNS Zones", str(len(topology.private_dns_zones))),
            ],
        ),
        _vnet_overview(topology),
        _topology_diagrams(topology),
        _peering_details(topology),
        _private_dns_zones(topology),
        _resource_inventory(topology),
    ]
    if include_analysis:
        sections.insert(1, _analysis_section(topology))
    return _page(
        title="Network Topology Report",
        subtitle="Static HTML export for netinspect topology summaries and network diagrams.",
        body_html="".join(sections),
    )


def generate_dns_html(topology: Topology) -> str:
    """Generate a static HTML DNS report."""
    resolver_usage, private_resolvers, public_resolvers, other_resolvers, azure_default = (
        _dns_inventory(topology)
    )
    sections = [
        _summary_cards(
            "DNS summary",
            [
                ("VNets", str(len(topology.vnets))),
                ("Azure DNS", str(azure_default)),
                ("Custom DNS", str(len(topology.vnets) - azure_default)),
                ("Private resolvers", str(len(private_resolvers))),
                ("Public resolvers", str(len(public_resolvers))),
                ("Private DNS zones", str(len(topology.private_dns_zones))),
            ],
        ),
        _dns_flow_diagram(topology),
        _dns_vnet_table(topology),
        _resolver_table("Private Resolver Inventory", private_resolvers, resolver_usage),
        _resolver_table("Public Resolver Inventory", public_resolvers, resolver_usage),
        _resolver_table("Other DNS Endpoints", other_resolvers, resolver_usage),
        _dns_zone_details(topology),
    ]
    return _page(
        title="DNS Configuration Report",
        subtitle=(
            "Static HTML export highlighting VNet DNS settings "
            "and configured private resolvers."
        ),
        body_html="".join(sections),
    )


def _page(*, title: str, subtitle: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
      :root {{
        color-scheme: light dark;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}

      body {{
        margin: 0;
        background: #0f172a;
        color: #e2e8f0;
      }}

      .report-shell {{
        max-width: 1400px;
        margin: 0 auto;
        padding: 32px 24px 48px;
      }}

      .report-header {{
        margin-bottom: 24px;
      }}

      .report-header h1 {{
        margin: 0 0 8px;
        font-size: 2rem;
      }}

      .report-header p {{
        margin: 0;
        color: #94a3b8;
      }}

      .section-card {{
        background: rgba(15, 23, 42, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        overflow: hidden;
      }}

      .section-card h2 {{
        margin-top: 0;
      }}

      .summary-grid, .inventory-grid {{
        display: grid;
        gap: 16px;
      }}

      .summary-grid {{
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      }}

      .inventory-grid {{
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      }}

      .summary-tile, .inventory-card, .vnet-card {{
        background: rgba(30, 41, 59, 0.75);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 14px;
        padding: 16px;
        overflow: hidden;
      }}

      .summary-tile strong {{
        display: block;
        font-size: 1.6rem;
        margin-bottom: 4px;
      }}

      .vnet-grid {{
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
      }}

      .vnet-meta, .chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 12px 0 0;
      }}

      .chip {{
        background: rgba(14, 165, 233, 0.14);
        border: 1px solid rgba(125, 211, 252, 0.24);
        border-radius: 999px;
        color: #bae6fd;
        display: inline-flex;
        font-size: 0.92rem;
        padding: 4px 10px;
      }}

      .chip.muted {{
        background: rgba(148, 163, 184, 0.12);
        border-color: rgba(148, 163, 184, 0.2);
        color: #cbd5e1;
      }}

      .table-scroll {{
        overflow-x: auto;
        margin-top: 12px;
      }}

      table {{
        border-collapse: collapse;
        width: 100%;
      }}

      th, td {{
        border: 1px solid rgba(148, 163, 184, 0.2);
        padding: 8px 10px;
        text-align: left;
        vertical-align: top;
        overflow-wrap: break-word;
        word-break: break-word;
      }}

      th {{
        background: rgba(30, 41, 59, 0.9);
        white-space: nowrap;
      }}

      code {{
        background: rgba(148, 163, 184, 0.14);
        border-radius: 4px;
        padding: 0.1rem 0.3rem;
      }}

      ul {{
        margin: 8px 0 0 20px;
        padding: 0;
      }}

      .empty-state {{
        color: #94a3b8;
      }}

      .mermaid-diagram {{
        background: rgba(30, 41, 59, 0.75);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 16px;
        overflow-x: auto;
      }}

      .mermaid-diagram h3 {{
        margin-top: 0;
        margin-bottom: 16px;
      }}

      .mermaid {{
        text-align: center;
      }}

      .mermaid svg {{
        max-width: 100%;
        height: auto;
      }}
    </style>
  </head>
  <body>
    <main class="report-shell">
      <header class="report-header">
        <h1>{escape(title)}</h1>
        <p>{escape(subtitle)}</p>
      </header>
      {body_html}
    </main>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
      mermaid.initialize({{
        startOnLoad: true,
        theme: 'dark',
        securityLevel: 'loose',
        flowchart: {{ useMaxWidth: true, htmlLabels: true }},
      }});
    </script>
  </body>
</html>
"""


def _summary_cards(title: str, items: list[tuple[str, str]]) -> str:
    tiles = "".join(
        (
            '<div class="summary-tile">'
            f"<strong>{escape(value)}</strong>"
            f"<span>{escape(label)}</span>"
            "</div>"
        )
        for label, value in items
    )
    return (
        '<section class="section-card">'
        f"<h2>{escape(title)}</h2>"
        f'<div class="summary-grid">{tiles}</div>'
        "</section>"
    )


def _analysis_section(topology: Topology) -> str:
    from netinspect.analysis.analyze import analyze_topology

    report = analyze_topology(topology)
    if not report.findings:
        return (
            '<section class="section-card"><h2>CAF/WAF Analysis</h2>'
            '<p class="empty-state">No findings — all checks passed.</p></section>'
        )

    rows = "".join(
        (
            "<tr>"
            f"<td>{escape(f.severity.value)}</td>"
            f"<td>{escape(f.category.value)}</td>"
            f"<td>{escape(f.title)}</td>"
            f"<td>{escape(f.resource_name or '—')}</td>"
            f"<td>{escape(f.recommendation)}</td>"
            "</tr>"
        )
        for f in report.sorted_findings()
    )
    return (
        '<section class="section-card"><h2>CAF/WAF Analysis</h2>'
        f"<p>{report.critical_count} critical, {report.warning_count} warning, "
        f"{report.info_count} info findings.</p>"
        "<table><thead><tr><th>Severity</th><th>Category</th><th>Finding</th>"
        "<th>Resource</th><th>Recommendation</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _vnet_overview(topology: Topology) -> str:
    if not topology.vnets:
        return (
            '<section class="section-card"><h2>Virtual Networks</h2>'
            '<p class="empty-state">No VNets discovered.</p></section>'
        )

    cards = []
    for vnet in topology.vnets:
        chips = [
            f'<span class="chip">{escape(address)}</span>'
            for address in (vnet.address_spaces or ["No address space"])
        ]
        dns_servers = vnet.dns_servers or ["Azure-provided DNS"]
        dns_chips = "".join(
            f'<span class="chip muted">{escape(server)}</span>' for server in dns_servers
        )
        subnet_rows = "".join(_subnet_row(subnet) for subnet in vnet.subnets)
        subnet_table = (
            '<div class="table-scroll">'
            "<table><thead><tr><th>Subnet</th><th>Prefix</th><th>NSG</th><th>Route Table</th>"
            f"</tr></thead><tbody>{subnet_rows}</tbody></table></div>"
            if subnet_rows
            else '<p class="empty-state">No subnets discovered.</p>'
        )
        cards.append(
            '<article class="vnet-card">'
            f"<h3>{escape(vnet.name)}</h3>"
            f"<p>{escape(vnet.location)} · {len(vnet.peerings)} peerings · "
            f"{len(vnet.subnets)} subnets</p>"
            f'<div class="chip-row">{"".join(chips)}</div>'
            '<div class="vnet-meta"><strong>DNS:</strong></div>'
            f'<div class="chip-row">{dns_chips}</div>'
            f"{subnet_table}"
            "</article>"
        )
    return (
        '<section class="section-card"><h2>Virtual Networks</h2>'
        f'<div class="vnet-grid">{"".join(cards)}</div></section>'
    )


def _topology_diagrams(topology: Topology) -> str:
    if not topology.vnets:
        return ""

    diagrams = generate_mermaid_diagrams(topology)
    if not diagrams:
        return ""

    blocks = []
    for title, mermaid_src in diagrams:
        blocks.append(
            f'<div class="mermaid-diagram">'
            f"<h3>{escape(title)}</h3>"
            f'<pre class="mermaid">{escape(mermaid_src)}</pre>'
            f"</div>"
        )
    return (
        '<section class="section-card"><h2>Network Topology Diagrams</h2>'
        f'{"" .join(blocks)}</section>'
    )


def _peering_details(topology: Topology) -> str:
    rows = []
    for vnet in topology.vnets:
        for peering in vnet.peerings:
            rows.append(
                "<tr>"
                f"<td>{escape(vnet.name)}</td>"
                f"<td>{escape(peering.remote_vnet_name)}</td>"
                f"<td>{escape(peering.state.value)}</td>"
                f"<td>{'Yes' if peering.allow_forwarded_traffic else 'No'}</td>"
                f"<td>{'Yes' if peering.allow_gateway_transit else 'No'}</td>"
                "</tr>"
            )
    if not rows:
        return (
            '<section class="section-card"><h2>Peering Details</h2>'
            '<p class="empty-state">No peerings found.</p></section>'
        )
    return (
        '<section class="section-card"><h2>Peering Details</h2>'
        "<table><thead><tr><th>Source VNet</th><th>Remote VNet</th><th>State</th>"
        "<th>Forwarded Traffic</th><th>Gateway Transit</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def _private_dns_zones(topology: Topology) -> str:
    if not topology.private_dns_zones:
        return (
            '<section class="section-card"><h2>Private DNS Zones</h2>'
            '<p class="empty-state">No private DNS zones found.</p></section>'
        )

    cards = []
    for zone in topology.private_dns_zones:
        linked = "".join(
            _zone_link_item(link)
            for link in zone.vnet_links
        ) or "<li>No VNet links</li>"
        cards.append(
            '<article class="inventory-card">'
            f"<h3>{escape(zone.name)}</h3>"
            f"<p><strong>Resource Group:</strong> <code>{escape(zone.resource_group)}</code></p>"
            f"<p><strong>Record Sets:</strong> {zone.record_count}</p>"
            f"<ul>{linked}</ul>"
            "</article>"
        )
    return (
        '<section class="section-card"><h2>Private DNS Zones</h2>'
        f'<div class="inventory-grid">{"".join(cards)}</div></section>'
    )


def _resource_inventory(topology: Topology) -> str:
    groups = [
        ("VPN Gateways", [gateway.name for gateway in topology.vpn_gateways]),
        ("NAT Gateways", [gateway.name for gateway in topology.nat_gateways]),
        ("Load Balancers", [lb.name for lb in topology.load_balancers]),
        ("Application Gateways", [gateway.name for gateway in topology.application_gateways]),
        ("Public IPs", [public_ip.name for public_ip in topology.public_ips]),
        ("Route Tables", [route_table.name for route_table in topology.route_tables]),
        ("NSGs", [nsg.name for nsg in topology.nsgs]),
    ]
    cards = []
    for title, items in groups:
        content = (
            "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"
            if items
            else '<p class="empty-state">None discovered.</p>'
        )
        cards.append(f'<article class="inventory-card"><h3>{escape(title)}</h3>{content}</article>')
    return (
        '<section class="section-card"><h2>Resource Inventory</h2>'
        f'<div class="inventory-grid">{"".join(cards)}</div></section>'
    )


def _subnet_row(subnet) -> str:
    nsg_name = subnet.nsg_id.split("/")[-1] if subnet.nsg_id else "—"
    route_table_name = subnet.route_table_id.split("/")[-1] if subnet.route_table_id else "—"
    return (
        "<tr>"
        f"<td>{escape(subnet.name)}</td>"
        f"<td><code>{escape(subnet.address_prefix)}</code></td>"
        f"<td>{escape(nsg_name)}</td>"
        f"<td>{escape(route_table_name)}</td>"
        "</tr>"
    )


def _zone_link_item(link) -> str:
    registration = "auto-registration enabled" if link.registration_enabled else "link only"
    return f"<li>{escape(link.vnet_name)} ({registration})</li>"


def _dns_flow_diagram(topology: Topology) -> str:
    """Build a Mermaid diagram showing VNet → DNS resolver → Private DNS zone relationships."""
    if not topology.vnets:
        return ""

    def _mid(name: str) -> str:
        return name.replace("-", "_").replace(".", "_").replace(" ", "_")

    lines = ["graph LR"]

    # Collect unique DNS servers and zone links
    dns_servers: set[str] = set()
    zone_vnet_links: dict[str, list[str]] = {}  # zone_name -> [vnet_names]
    for zone in topology.private_dns_zones:
        for link in zone.vnet_links:
            zone_vnet_links.setdefault(zone.name, []).append(link.vnet_name)

    for vnet in topology.vnets:
        vid = _mid(vnet.name)
        lines.append(f'    {vid}["{vnet.name}"]')

        if vnet.dns_servers:
            for server in vnet.dns_servers:
                sid = _mid(f"dns_{server}")
                dns_servers.add(server)
                lines.append(f"    {vid} --> {sid}")
        else:
            lines.append(f"    {vid} -.->|Azure DNS| azure_dns")

    # DNS server nodes
    for server in sorted(dns_servers):
        sid = _mid(f"dns_{server}")
        scope = _resolver_scope(server)
        icon = "🔒" if scope == "private" else "🌐"
        lines.append(f'    {sid}("{icon} {server}")')

    # Azure DNS node (if any VNet uses default)
    if any(not v.dns_servers for v in topology.vnets):
        lines.append('    azure_dns(("☁️ Azure DNS"))')

    # Private DNS zone nodes and links
    for zone_name, vnet_names in zone_vnet_links.items():
        zid = _mid(f"zone_{zone_name}")
        lines.append(f'    {zid}[/"📛 {zone_name}"/]')
        for vnet_name in vnet_names:
            vid = _mid(vnet_name)
            lines.append(f"    {vid} -.->|DNS link| {zid}")

    mermaid_src = "\n".join(lines)
    return (
        '<section class="section-card"><h2>DNS Resolution Flow</h2>'
        '<div class="mermaid-diagram">'
        f'<pre class="mermaid">{escape(mermaid_src)}</pre>'
        "</div></section>"
    )


def _dns_inventory(
    topology: Topology,
) -> tuple[dict[str, set[str]], set[str], set[str], set[str], int]:
    resolver_usage: dict[str, set[str]] = {}
    private_resolvers: set[str] = set()
    public_resolvers: set[str] = set()
    other_resolvers: set[str] = set()
    azure_default = 0

    for vnet in topology.vnets:
        if not vnet.dns_servers:
            azure_default += 1
            continue
        for resolver in vnet.dns_servers:
            resolver_usage.setdefault(resolver, set()).add(vnet.name)
            scope = _resolver_scope(resolver)
            if scope == "private":
                private_resolvers.add(resolver)
            elif scope == "public":
                public_resolvers.add(resolver)
            else:
                other_resolvers.add(resolver)

    return resolver_usage, private_resolvers, public_resolvers, other_resolvers, azure_default


def _dns_vnet_table(topology: Topology) -> str:
    rows = []
    for vnet in topology.vnets:
        if not vnet.dns_servers:
            rows.append(
                f"<tr><td>{escape(vnet.name)}</td><td>Azure Default</td>"
                "<td>Azure-provided</td><td>—</td><td>—</td></tr>"
            )
            continue

        private = [value for value in vnet.dns_servers if _resolver_scope(value) == "private"]
        public = [value for value in vnet.dns_servers if _resolver_scope(value) == "public"]
        rows.append(
            f"<tr><td>{escape(vnet.name)}</td><td>Custom</td>"
            f"<td>{', '.join(f'<code>{escape(value)}</code>' for value in vnet.dns_servers)}</td>"
            f"<td>{escape(', '.join(private) or '—')}</td>"
            f"<td>{escape(', '.join(public) or '—')}</td></tr>"
        )

    return (
        '<section class="section-card"><h2>VNet DNS Configuration</h2>'
        "<table><thead><tr><th>VNet</th><th>DNS Mode</th><th>Configured Servers</th>"
        "<th>Private Resolvers</th><th>Public Resolvers</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def _resolver_table(
    title: str, resolvers: set[str], resolver_usage: dict[str, set[str]],
) -> str:
    if not resolvers:
        return (
            f'<section class="section-card"><h2>{escape(title)}</h2>'
            '<p class="empty-state">None identified.</p></section>'
        )
    rows = "".join(
        f"<tr><td><code>{escape(resolver)}</code></td>"
        f"<td>{escape(', '.join(sorted(resolver_usage[resolver])))}</td></tr>"
        for resolver in sorted(resolvers)
    )
    return (
        f'<section class="section-card"><h2>{escape(title)}</h2>'
        "<table><thead><tr><th>Resolver</th><th>Used By VNets</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _dns_zone_details(topology: Topology) -> str:
    if not topology.private_dns_zones:
        return (
            '<section class="section-card"><h2>Private DNS Zones</h2>'
            '<p class="empty-state">No private DNS zones found.</p></section>'
        )

    rows = []
    for zone in topology.private_dns_zones:
        linked_vnets = ", ".join(sorted(link.vnet_name for link in zone.vnet_links)) or "None"
        rows.append(
            "<tr>"
            f"<td>{escape(zone.name)}</td>"
            f"<td><code>{escape(zone.resource_group)}</code></td>"
            f"<td>{zone.record_count}</td>"
            f"<td>{escape(linked_vnets)}</td>"
            "</tr>"
        )
    return (
        '<section class="section-card"><h2>Private DNS Zones</h2>'
        "<table><thead><tr><th>Zone</th><th>Resource Group</th><th>Record Sets</th>"
        "<th>Linked VNets</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def _resolver_scope(value: str) -> str:
    try:
        return "private" if ip_address(value).is_private else "public"
    except ValueError:
        return "other"
