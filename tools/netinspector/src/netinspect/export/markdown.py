"""Markdown report generation for network topology."""

from __future__ import annotations

from pathlib import Path

from netinspect.export.mermaid import generate_mermaid_diagrams
from netinspect.models.types import Topology


def generate_report(topology: Topology, *, include_analysis: bool = False) -> str:
    """Generate a full Markdown report for the network topology."""
    sections = [
        _header(topology),
    ]
    if include_analysis:
        sections.append(_findings_section(topology))
    sections.extend([
        _vnet_summary(topology),
        _topology_diagram(topology),
        _peering_matrix(topology),
        _vpn_gateways_section(topology),
        _local_gateways_section(topology),
        _expressroute_section(topology),
        _bgp_section(topology),
        _vwan_section(topology),
        _load_balancers_section(topology),
        _app_gateways_section(topology),
        _nat_gateways_section(topology),
        _public_ips_section(topology),
        _private_dns_section(topology),
        _route_tables_section(topology),
        _nsg_section(topology),
    ])
    return "\n\n".join(sections)


def export_report(
    topology: Topology, output_path: Path, *, include_analysis: bool = False,
) -> None:
    """Generate and write the Markdown report to a file."""
    report = generate_report(topology, include_analysis=include_analysis)
    output_path.write_text(report, encoding="utf-8")


def _header(topology: Topology) -> str:
    sub_ids = topology.subscription_ids or [topology.subscription_id]
    sub_str = ", ".join(f"`{s}`" for s in sub_ids if s)
    lines = [
        "# Network Topology Report",
        "",
        f"**Subscription(s):** {sub_str}  ",
        f"**VNets:** {len(topology.vnets)}  ",
        f"**Route Tables:** {len(topology.route_tables)}  ",
        f"**NSGs:** {len(topology.nsgs)}  ",
        f"**NAT Gateways:** {len(topology.nat_gateways)}  ",
        f"**VPN Gateways:** {len(topology.vpn_gateways)}  ",
        f"**Public IPs:** {len(topology.public_ips)}  ",
        f"**Private DNS Zones:** {len(topology.private_dns_zones)}  ",
        f"**Local Network Gateways:** {len(topology.local_network_gateways)}  ",
        f"**ExpressRoute Circuits:** {len(topology.expressroute_circuits)}  ",
        f"**BGP Peers:** {len(topology.bgp_peers)}  ",
        f"**Virtual WANs:** {len(topology.virtual_wans)}  ",
        f"**Virtual Hubs:** {len(topology.virtual_hubs)}  ",
        f"**Load Balancers:** {len(topology.load_balancers)}  ",
        f"**Application Gateways:** {len(topology.application_gateways)}",
    ]
    return "\n".join(lines)


def _findings_section(topology: Topology) -> str:
    from netinspect.analysis.analyze import analyze_topology

    report = analyze_topology(topology)
    if not report.findings:
        return "## CAF/WAF Analysis\n\n✅ No findings — all checks passed."

    findings = report.sorted_findings()
    lines = [
        "## CAF/WAF Analysis",
        "",
        f"**{report.critical_count}** 🔴 Critical  "
        f"**{report.warning_count}** 🟡 Warning  "
        f"**{report.info_count}** 🔵 Info  "
        f"— **{len(report.findings)} total findings**",
        "",
        "| Severity | Category | Finding | Resource | Recommendation |",
        "|----------|----------|---------|----------|----------------|",
    ]

    for f in findings:
        resource = f.resource_name or "—"
        lines.append(
            f"| {f.severity_icon} {f.severity.value} | "
            f"{f.category.value} | "
            f"{f.title} | {resource} | "
            f"{f.recommendation} |"
        )

    return "\n".join(lines)


def _vnet_summary(topology: Topology) -> str:
    lines = ["## Virtual Networks", ""]
    for vnet in topology.vnets:
        addr = ", ".join(vnet.address_spaces) or "N/A"
        dns = ", ".join(vnet.dns_servers) or "Azure Default"
        lines.append(f"<details>")
        lines.append(f"<summary><strong>{vnet.name}</strong> — <code>{addr}</code> ({vnet.location}, {len(vnet.subnets)} subnets, {len(vnet.peerings)} peerings)</summary>")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{vnet.resource_group}` |")
        lines.append(f"| Location | {vnet.location} |")
        lines.append(f"| Address Spaces | `{addr}` |")
        lines.append(f"| DNS Servers | {dns} |")
        lines.append(f"| Subnets | {len(vnet.subnets)} |")
        lines.append(f"| Peerings | {len(vnet.peerings)} |")
        lines.append("")

        if vnet.subnets:
            lines.append("**Subnets:**")
            lines.append("")
            lines.append(
                "| Name | Address Prefix | NSG | Route Table | NAT GW | Delegations |"
            )
            lines.append(
                "|------|---------------|-----|-------------|--------|-------------|"
            )
            for s in vnet.subnets:
                nsg = s.nsg_id.split("/")[-1] if s.nsg_id else "—"
                rt = s.route_table_id.split("/")[-1] if s.route_table_id else "—"
                nat = s.nat_gateway_id.split("/")[-1] if s.nat_gateway_id else "—"
                deleg = ", ".join(s.delegations) or "—"
                lines.append(
                    f"| {s.name} | `{s.address_prefix}` "
                    f"| {nsg} | {rt} | {nat} | {deleg} |"
                )
            lines.append("")

        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def _topology_diagram(topology: Topology) -> str:
    diagrams = generate_mermaid_diagrams(topology)
    if not diagrams:
        return "## Network Topology Diagram\n\nNo VNets discovered."

    lines = ["## Network Topology Diagrams", ""]

    for i, (title, mermaid) in enumerate(diagrams):
        if i > 0:
            lines.append("---")
            lines.append("")
        lines.append(f"### {title}")
        lines.append("")
        lines.append("```mermaid")
        lines.append(mermaid)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _peering_matrix(topology: Topology) -> str:
    if not any(v.peerings for v in topology.vnets):
        return "## Peering\n\nNo peerings found."

    lines = ["## Peering Details", ""]
    lines.append(
        "| Source VNet | Remote VNet | State | Fwd Traffic | GW Transit | Remote GW |"
    )
    lines.append(
        "|-------------|-------------|-------|-------------|------------|-----------|"
    )

    for vnet in topology.vnets:
        for p in vnet.peerings:
            fwd = "✅" if p.allow_forwarded_traffic else "❌"
            gw = "✅" if p.allow_gateway_transit else "❌"
            rgw = "✅" if p.use_remote_gateways else "❌"
            state_icon = "🟢" if p.state.value == "Connected" else "🔴"
            lines.append(
                f"| {vnet.name} | {p.remote_vnet_name} | "
                f"{state_icon} {p.state.value} | {fwd} | {gw} | {rgw} |"
            )

    return "\n".join(lines)


def _build_pip_map(topology: Topology) -> dict[str, tuple[str, str]]:
    """Build a map from PIP resource ID to (name, ip_address)."""
    return {
        pip.id: (pip.name, pip.ip_address or "(not allocated)")
        for pip in topology.public_ips
    }


def _vpn_gateways_section(topology: Topology) -> str:
    if not topology.vpn_gateways:
        return "## VPN Gateways\n\nNo VPN/ExpressRoute gateways found."

    pip_map = _build_pip_map(topology)

    lines = ["## VPN / ExpressRoute Gateways", ""]
    for gw in topology.vpn_gateways:
        is_er = gw.gateway_type == "ExpressRoute"
        vnet_name = gw.vnet_id.split("/")[-1] if gw.vnet_id else "—"
        lines.append(f"### {gw.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{gw.resource_group}` |")
        lines.append(f"| VNet | **{vnet_name}** |")
        lines.append(f"| Type | {gw.gateway_type} |")
        if not is_er:
            lines.append(f"| VPN Type | {gw.vpn_type or '—'} |")
        lines.append(f"| SKU | {gw.sku or '—'} |")
        if is_er:
            # ER gateways use BGP inherently via the ER circuit
            bgp_info = f"ASN {gw.bgp_asn}" if gw.bgp_asn else "Inherited from circuit"
            lines.append(f"| BGP | {bgp_info} |")
        else:
            bgp_info = f"ASN {gw.bgp_asn}" if gw.bgp_enabled else "Disabled"
            lines.append(f"| BGP | {bgp_info} |")
        if gw.bgp_peering_address:
            lines.append(
                f"| BGP Peering Address | {gw.bgp_peering_address} |"
            )
        active = "Yes" if gw.active_active else "No"
        lines.append(f"| Active-Active | {active} |")

        # Show public IPs
        for pip_id in gw.public_ips:
            pip_info = pip_map.get(pip_id)
            if pip_info:
                lines.append(
                    f"| Public IP | `{pip_info[1]}` ({pip_info[0]}) |"
                )
            else:
                pip_name = pip_id.split("/")[-1]
                lines.append(f"| Public IP | {pip_name} |")
        lines.append("")

        if gw.connections:
            lines.append("**Connections:**")
            lines.append("")
            if is_er:
                lines.append(
                    "| Name | Type | Status | ER Circuit | "
                    "FastPath | Routing Weight |"
                )
                lines.append(
                    "|------|------|--------|------------|"
                    "----------|----------------|"
                )
                for c in gw.connections:
                    remote = (
                        c.remote_gateway_id.split("/")[-1]
                        if c.remote_gateway_id else "—"
                    )
                    status_icon = "🟢" if c.status in ("Connected", "Succeeded") else "🔴"
                    fastpath = "✅" if c.express_route_gateway_bypass else "❌"
                    lines.append(
                        f"| {c.name} | {c.connection_type} | "
                        f"{status_icon} {c.status} | {remote} | "
                        f"{fastpath} | {c.routing_weight} |"
                    )
            else:
                lines.append(
                    "| Name | Type | Status | BGP | Remote Gateway |"
                )
                lines.append(
                    "|------|------|--------|-----|----------------|"
                )
                for c in gw.connections:
                    bgp = "✅" if c.enable_bgp else "❌"
                    remote = (
                        c.remote_gateway_id.split("/")[-1]
                        if c.remote_gateway_id else "—"
                    )
                    status_icon = "🟢" if c.status == "Connected" else "🔴"
                    lines.append(
                        f"| {c.name} | {c.connection_type} | "
                        f"{status_icon} {c.status} | {bgp} | {remote} |"
                    )
            lines.append("")

    return "\n".join(lines)


def _local_gateways_section(topology: Topology) -> str:
    if not topology.local_network_gateways:
        return "## Local Network Gateways\n\nNo local network gateways found."

    lines = ["## Local Network Gateways", ""]
    for lgw in topology.local_network_gateways:
        lines.append(f"### {lgw.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{lgw.resource_group}` |")
        lines.append(f"| Gateway IP | `{lgw.gateway_ip or '—'}` |")
        prefixes = ", ".join(
            f"`{p}`" for p in lgw.address_prefixes
        ) or "None"
        lines.append(f"| Address Prefixes | {prefixes} |")
        if lgw.bgp_asn:
            lines.append(f"| BGP ASN | {lgw.bgp_asn} |")
            lines.append(
                f"| BGP Peer Address | "
                f"`{lgw.bgp_peering_address or '—'}` |"
            )
        if lgw.fqdn:
            lines.append(f"| FQDN | `{lgw.fqdn}` |")
        lines.append("")

    return "\n".join(lines)


def _expressroute_section(topology: Topology) -> str:
    if not topology.expressroute_circuits:
        return "## ExpressRoute Circuits\n\nNo ExpressRoute circuits found."

    lines = ["## ExpressRoute Circuits", ""]
    for er in topology.expressroute_circuits:
        lines.append(f"### {er.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{er.resource_group}` |")
        lines.append(f"| Location | {er.location} |")
        lines.append(
            f"| Service Provider | {er.service_provider or '—'} |"
        )
        lines.append(
            f"| Peering Location | {er.peering_location or '—'} |"
        )
        lines.append(
            f"| Bandwidth | {er.bandwidth_mbps or '—'} Mbps |"
        )
        lines.append(
            f"| SKU | {er.sku_tier or '—'} / "
            f"{er.sku_family or '—'} |"
        )
        lines.append(
            f"| Circuit State | {er.circuit_provisioning_state or '—'} |"
        )
        lines.append(
            f"| Provider State | "
            f"{er.service_provider_provisioning_state or '—'} |"
        )
        lines.append("")

        if er.peerings:
            lines.append("**Peerings:**")
            lines.append("")
            lines.append(
                "| Type | State | Azure ASN | Peer ASN | "
                "VLAN | Primary Prefix | Secondary Prefix |"
            )
            lines.append(
                "|------|-------|-----------|----------|"
                "------|----------------|------------------|"
            )
            for p in er.peerings:
                lines.append(
                    f"| {p.peering_type} | {p.state} | "
                    f"{p.azure_asn or '—'} | {p.peer_asn or '—'} | "
                    f"{p.vlan_id or '—'} | "
                    f"`{p.primary_prefix or '—'}` | "
                    f"`{p.secondary_prefix or '—'}` |"
                )
            lines.append("")

    return "\n".join(lines)


def _bgp_section(topology: Topology) -> str:
    if not topology.bgp_peers:
        return "## BGP Peers\n\nNo BGP peers found."

    lines = ["## BGP Peers", ""]
    lines.append(
        "| Gateway | Neighbor | ASN | State | Routes Received | "
        "Connected Duration |"
    )
    lines.append(
        "|---------|----------|-----|-------|-----------------|"
        "-------------------|"
    )
    for bp in topology.bgp_peers:
        state_icon = "🟢" if bp.state == "Connected" else "🔴"
        duration = bp.connected_duration or "—"
        lines.append(
            f"| {bp.gateway_name} | `{bp.neighbor}` | "
            f"{bp.asn or '—'} | {state_icon} {bp.state} | "
            f"{bp.routes_received} | {duration} |"
        )

    return "\n".join(lines)


def _vwan_section(topology: Topology) -> str:
    if not topology.virtual_wans and not topology.virtual_hubs:
        return "## Virtual WAN\n\nNo Virtual WAN resources found."

    lines = ["## Virtual WAN", ""]

    for wan in topology.virtual_wans:
        lines.append(f"### vWAN: {wan.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{wan.resource_group}` |")
        lines.append(f"| Type | {wan.wan_type} |")
        b2b = "✅" if wan.allow_branch_to_branch else "❌"
        v2v = "✅" if wan.allow_vnet_to_vnet else "❌"
        lines.append(f"| Branch-to-Branch | {b2b} |")
        lines.append(f"| VNet-to-VNet | {v2v} |")
        lines.append(f"| Hubs | {len(wan.hub_ids)} |")
        lines.append("")

    for hub in topology.virtual_hubs:
        lines.append(f"### Hub: {hub.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{hub.resource_group}` |")
        lines.append(f"| Location | {hub.location} |")
        lines.append(
            f"| Address Prefix | `{hub.address_prefix or '—'}` |"
        )
        lines.append(f"| SKU | {hub.sku or '—'} |")
        lines.append(f"| Routing State | {hub.routing_state} |")
        lines.append(
            f"| Provisioning State | {hub.provisioning_state} |"
        )
        if hub.vpn_gateway_id:
            gw_name = hub.vpn_gateway_id.split("/")[-1]
            lines.append(f"| VPN Gateway | {gw_name} |")
        if hub.er_gateway_id:
            gw_name = hub.er_gateway_id.split("/")[-1]
            lines.append(f"| ER Gateway | {gw_name} |")
        if hub.p2s_gateway_id:
            gw_name = hub.p2s_gateway_id.split("/")[-1]
            lines.append(f"| P2S Gateway | {gw_name} |")
        lines.append("")

        if hub.vnet_connections:
            lines.append("**VNet Connections:**")
            lines.append("")
            lines.append(
                "| Name | Remote VNet | Internet Security | State |"
            )
            lines.append(
                "|------|-------------|-------------------|-------|"
            )
            for c in hub.vnet_connections:
                isec = "✅" if c.enable_internet_security else "❌"
                lines.append(
                    f"| {c.name} | {c.remote_vnet_name} | "
                    f"{isec} | {c.provisioning_state} |"
                )
            lines.append("")

        if hub.route_tables:
            lines.append("**Route Tables:**")
            lines.append("")
            for rt in hub.route_tables:
                lines.append(f"*{rt.name}* ({rt.provisioning_state})")
                lines.append("")
                if rt.routes:
                    lines.append(
                        "| Name | Dest Type | Destinations | "
                        "Next Hop Type | Next Hop |"
                    )
                    lines.append(
                        "|------|-----------|-------------|"
                        "--------------|----------|"
                    )
                    for r in rt.routes:
                        lines.append(
                            f"| {r.get('name', '')} | "
                            f"{r.get('destination_type', '')} | "
                            f"{r.get('destinations', '')} | "
                            f"{r.get('next_hop_type', '')} | "
                            f"{r.get('next_hop', '')} |"
                        )
                    lines.append("")
                if rt.associated_connections:
                    lines.append(
                        f"Associated: {', '.join(rt.associated_connections)}"
                    )
                if rt.propagating_connections:
                    lines.append(
                        f"Propagating: "
                        f"{', '.join(rt.propagating_connections)}"
                    )
                lines.append("")

    return "\n".join(lines)


def _load_balancers_section(topology: Topology) -> str:
    if not topology.load_balancers:
        return "## Load Balancers\n\nNo load balancers found."

    pip_map = _build_pip_map(topology)

    lines = ["## Load Balancers", ""]
    for lb in topology.load_balancers:
        lb_type = "Internal" if lb.is_internal else "Public"
        lines.append(f"### {lb.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{lb.resource_group}` |")
        lines.append(f"| SKU | {lb.sku} |")
        lines.append(f"| Type | {lb_type} |")
        lines.append("")

        if lb.frontends:
            lines.append("**Frontends:**")
            lines.append("")
            lines.append("| Name | Private IP | Public IP |")
            lines.append("|------|-----------|-----------|")
            for fe in lb.frontends:
                pip_str = "—"
                if fe.public_ip_id:
                    pip_info = pip_map.get(fe.public_ip_id)
                    if pip_info:
                        pip_str = f"`{pip_info[1]}` ({pip_info[0]})"
                    else:
                        pip_str = fe.public_ip_id.split("/")[-1]
                priv = f"`{fe.private_ip}`" if fe.private_ip else "—"
                lines.append(f"| {fe.name} | {priv} | {pip_str} |")
            lines.append("")

        if lb.rules:
            lines.append("**Rules:**")
            lines.append("")
            lines.append(
                "| Name | Frontend | Backend Pool | "
                "FE Port | BE Port | Protocol |"
            )
            lines.append(
                "|------|----------|-------------|"
                "---------|---------|----------|"
            )
            for r in lb.rules:
                lines.append(
                    f"| {r.name} | {r.frontend_name} | "
                    f"{r.backend_pool_name} | {r.frontend_port} | "
                    f"{r.backend_port} | {r.protocol} |"
                )
            lines.append("")

        if lb.probes:
            lines.append("**Health Probes:**")
            lines.append("")
            lines.append("| Name | Protocol | Port | Interval |")
            lines.append("|------|----------|------|----------|")
            for p in lb.probes:
                lines.append(
                    f"| {p.name} | {p.protocol} | "
                    f"{p.port} | {p.interval}s |"
                )
            lines.append("")

    return "\n".join(lines)


def _app_gateways_section(topology: Topology) -> str:
    if not topology.application_gateways:
        return "## Application Gateways\n\nNo application gateways found."

    pip_map = _build_pip_map(topology)

    lines = ["## Application Gateways", ""]
    for agw in topology.application_gateways:
        waf = f"✅ {agw.waf_mode}" if agw.waf_enabled else "❌ Disabled"
        lines.append(f"### {agw.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{agw.resource_group}` |")
        lines.append(f"| SKU | {agw.sku_tier} / {agw.sku_name} |")
        lines.append(f"| Capacity | {agw.capacity or 'Autoscale'} |")
        lines.append(f"| WAF | {waf} |")
        for pip_id in agw.public_ip_ids:
            pip_info = pip_map.get(pip_id)
            if pip_info:
                lines.append(
                    f"| Public IP | `{pip_info[1]}` ({pip_info[0]}) |"
                )
        lines.append("")

        if agw.listeners:
            lines.append("**Listeners:**")
            lines.append("")
            lines.append(
                "| Name | Protocol | Port | Host |"
            )
            lines.append(
                "|------|----------|------|------|"
            )
            for lis in agw.listeners:
                host = lis.host_name or "*"
                lines.append(
                    f"| {lis.name} | {lis.protocol} | "
                    f"{lis.port} | {host} |"
                )
            lines.append("")

        if agw.routing_rules:
            lines.append("**Routing Rules:**")
            lines.append("")
            lines.append(
                "| Name | Type | Listener | Backend Pool | Priority |"
            )
            lines.append(
                "|------|------|----------|-------------|----------|"
            )
            for r in agw.routing_rules:
                lines.append(
                    f"| {r.name} | {r.rule_type} | "
                    f"{r.listener_name} | {r.backend_pool_name} | "
                    f"{r.priority or '—'} |"
                )
            lines.append("")

    return "\n".join(lines)


def _nat_gateways_section(topology: Topology) -> str:
    if not topology.nat_gateways:
        return "## NAT Gateways\n\nNo NAT gateways found."

    pip_map = _build_pip_map(topology)

    lines = ["## NAT Gateways", ""]
    for ng in topology.nat_gateways:
        lines.append(f"### {ng.name}")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Resource Group | `{ng.resource_group}` |")
        lines.append(f"| SKU | {ng.sku} |")
        lines.append(
            f"| Idle Timeout | {ng.idle_timeout_minutes} min |"
        )

        # Show resolved public IPs
        for pip_id in ng.public_ip_addresses:
            pip_info = pip_map.get(pip_id)
            if pip_info:
                lines.append(
                    f"| Public IP | `{pip_info[1]}` ({pip_info[0]}) |"
                )
            else:
                pip_name = pip_id.split("/")[-1]
                lines.append(f"| Public IP | {pip_name} |")

        subnets = [
            s.split("/")[-1] for s in ng.associated_subnets
        ] or ["None"]
        lines.append(
            f"| Associated Subnets | {', '.join(subnets)} |"
        )
        lines.append("")

    return "\n".join(lines)


def _public_ips_section(topology: Topology) -> str:
    if not topology.public_ips:
        return "## Public IP Addresses\n\nNo public IPs found."

    lines = ["## Public IP Addresses", ""]
    lines.append(
        "| Name | IP Address | SKU | Allocation | Associated To | FQDN |"
    )
    lines.append(
        "|------|-----------|-----|------------|---------------|------|"
    )
    for pip in topology.public_ips:
        ip = pip.ip_address or "(not allocated)"
        assoc = pip.associated_resource_type or "—"
        if pip.associated_resource_id:
            assoc_name = pip.associated_resource_id.split("/")[-1]
            assoc = f"{pip.associated_resource_type}: {assoc_name}"
        fqdn = pip.dns_fqdn or "—"
        lines.append(
            f"| {pip.name} | `{ip}` | {pip.sku} | "
            f"{pip.allocation_method} | {assoc} | {fqdn} |"
        )

    return "\n".join(lines)


def _private_dns_section(topology: Topology) -> str:
    if not topology.private_dns_zones:
        return "## Private DNS Zones\n\nNo private DNS zones found."

    lines = ["## Private DNS Zones", ""]
    for zone in topology.private_dns_zones:
        lines.append(f"### {zone.name}")
        lines.append("")
        lines.append(f"- **Resource Group:** `{zone.resource_group}`")
        lines.append(f"- **Record Sets:** {zone.record_count}")
        lines.append("")

        if zone.vnet_links:
            lines.append("**VNet Links:**")
            lines.append("")
            lines.append("| VNet | Registration |")
            lines.append("|------|-------------|")
            for link in zone.vnet_links:
                reg = "✅ Auto-register" if link.registration_enabled else "❌"
                lines.append(f"| {link.vnet_name} | {reg} |")
            lines.append("")
        else:
            lines.append("*No VNet links.*")
            lines.append("")

    return "\n".join(lines)


def _route_tables_section(topology: Topology) -> str:
    if not topology.route_tables:
        return "## Route Tables\n\nNo route tables found."

    lines = ["## Route Tables", ""]
    for rt in topology.route_tables:
        bgp = "🚫 Disabled" if rt.disable_bgp_route_propagation else "✅ Enabled"
        lines.append(f"### {rt.name}")
        lines.append("")
        lines.append(f"- **Resource Group:** `{rt.resource_group}`")
        lines.append(f"- **BGP Route Propagation:** {bgp}")
        associated = [
            s.split("/")[-3] + "/" + s.split("/")[-1]
            for s in rt.associated_subnets
        ] or ["None"]
        lines.append(f"- **Associated Subnets:** {', '.join(associated)}")
        lines.append("")

        if rt.routes:
            lines.append("| Route Name | Prefix | Next Hop Type | Next Hop IP |")
            lines.append("|------------|--------|---------------|-------------|")
            for r in rt.routes:
                ip = r.next_hop_ip or "—"
                lines.append(f"| {r.name} | `{r.address_prefix}` | {r.next_hop_type} | {ip} |")
            lines.append("")

    return "\n".join(lines)


def _nsg_section(topology: Topology) -> str:
    if not topology.nsgs:
        return "## Network Security Groups\n\nNo NSGs found."

    lines = ["## Network Security Groups", ""]
    for nsg in topology.nsgs:
        lines.append(f"### {nsg.name}")
        lines.append("")
        lines.append(f"- **Resource Group:** `{nsg.resource_group}`")
        associated_subnets = [s.split("/")[-1] for s in nsg.associated_subnets] or ["None"]
        lines.append(f"- **Associated Subnets:** {', '.join(associated_subnets)}")
        lines.append("")

        # Only show custom rules (not default) to keep report readable
        custom_rules = [r for r in nsg.rules if not r.name.startswith("AllowVnetIn")
                        and not r.name.startswith("AllowAzureLoadBalancerIn")
                        and not r.name.startswith("DenyAllIn")
                        and not r.name.startswith("AllowVnetOut")
                        and not r.name.startswith("AllowInternetOut")
                        and not r.name.startswith("DenyAllOut")]

        if custom_rules:
            lines.append("**Custom Rules:**")
            lines.append("")
            lines.append(
                "| Pri | Name | Dir | Access | Proto | Source | Dest | Port |"
            )
            lines.append(
                "|-----|------|-----|--------|-------|--------|------|------|"
            )
            for r in custom_rules:
                src = r.source_address_prefix or ", ".join(r.source_address_prefixes) or "*"
                dst = (
                    r.destination_address_prefix
                    or ", ".join(r.destination_address_prefixes) or "*"
                )
                port = r.destination_port_range or "*"
                icon = "✅" if r.access.value == "Allow" else "🚫"
                lines.append(
                    f"| {r.priority} | {r.name} | {r.direction.value} | "
                    f"{icon} {r.access.value} | {r.protocol} | {src} | {dst} | {port} |"
                )
            lines.append("")
        else:
            lines.append("*Only default rules — no custom rules defined.*")
            lines.append("")

    return "\n".join(lines)
