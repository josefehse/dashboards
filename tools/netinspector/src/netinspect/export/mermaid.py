"""Mermaid diagram generation for network topology."""

from __future__ import annotations

from netinspect.models.types import Topology


def generate_mermaid_diagrams(topology: Topology) -> list[tuple[str, str]]:
    """Generate separate Mermaid diagrams grouped by connected VNet clusters.

    Returns a list of (title, mermaid_string) tuples — one per connected
    component.  Standalone VNets get their own diagram; peered VNets share one.
    """

    # --- helpers ---
    def node_id(name: str) -> str:
        return name.replace("-", "_").replace(".", "_").replace(" ", "_")

    # Build PIP lookups
    pip_by_id: dict[str, tuple[str, str]] = {}
    pip_by_resource: dict[str, list[tuple[str, str]]] = {}
    for pip in topology.public_ips:
        entry = (pip.name, pip.ip_address or "dynamic")
        if pip.id:
            pip_by_id[pip.id.lower()] = entry
        if pip.associated_resource_id:
            pip_by_resource.setdefault(
                pip.associated_resource_id, []
            ).append(entry)

    # --- union-find to discover connected components ---
    vnet_names = [v.name for v in topology.vnets]
    parent: dict[str, str] = {n: n for n in vnet_names}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Union peered VNets
    for vnet in topology.vnets:
        for p in vnet.peerings:
            if p.remote_vnet_name in parent:
                union(vnet.name, p.remote_vnet_name)

    # Union VNets connected via vWAN hubs
    for hub in topology.virtual_hubs:
        hub_vnets = [
            c.remote_vnet_name for c in hub.vnet_connections
            if c.remote_vnet_name in parent
        ]
        for i in range(1, len(hub_vnets)):
            union(hub_vnets[0], hub_vnets[i])

    # Group VNets by root
    groups: dict[str, list[str]] = {}
    for name in vnet_names:
        root = find(name)
        groups.setdefault(root, []).append(name)

    vnet_map = {v.name: v for v in topology.vnets}

    # --- build index: which VNet "owns" each subnet ID ---
    subnet_to_vnet: dict[str, str] = {}
    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            subnet_to_vnet[subnet.id.lower()] = vnet.name

    # --- generate one diagram per group ---
    diagrams: list[tuple[str, str]] = []

    for _root, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        member_set = set(members)
        is_standalone = len(members) == 1 and not any(
            vnet_map[members[0]].peerings
        )

        if is_standalone:
            title = f"{members[0]}"
        else:
            title = " ↔ ".join(sorted(members))

        lines = ["graph LR"]

        # VNet subgraphs with subnets
        for vname in sorted(members):
            vnet = vnet_map[vname]
            vid = node_id(vname)
            lines.append(f"    subgraph {vid}[\"🔷 {vname}\"]")
            lines.append("        direction TB")
            addr = ", ".join(vnet.address_spaces)
            lines.append(f"        {vid}_info[\"{addr}\"]")
            for subnet in vnet.subnets:
                sid = node_id(f"{vname}_{subnet.name}")
                lines.append(
                    f"        {sid}[\"{subnet.name}<br/>"
                    f"{subnet.address_prefix}\"]"
                )
            lines.append("    end")

        # Peering edges (deduplicated)
        peering_pairs: set[tuple[str, str]] = set()
        for vname in members:
            vnet = vnet_map[vname]
            vid = node_id(vname)
            for peering in vnet.peerings:
                remote_vid = node_id(peering.remote_vnet_name)
                pair = tuple(sorted([vid, remote_vid]))
                if pair not in peering_pairs:
                    peering_pairs.add(pair)
                    state_icon = (
                        "✅" if peering.state.value == "Connected" else "❌"
                    )
                    label_parts = [state_icon]
                    if peering.allow_forwarded_traffic:
                        label_parts.append("fwd")
                    if peering.allow_gateway_transit:
                        label_parts.append("gw-transit")
                    if peering.use_remote_gateways:
                        label_parts.append("remote-gw")
                    label = " ".join(label_parts)
                    lines.append(
                        f"    {pair[0]} <-->|{label}| {pair[1]}"
                    )

        # NSG associations
        for vname in members:
            vnet = vnet_map[vname]
            for subnet in vnet.subnets:
                if subnet.nsg_id:
                    nsg_name = subnet.nsg_id.split("/")[-1]
                    sid = node_id(f"{vname}_{subnet.name}")
                    nid = node_id(nsg_name)
                    lines.append(
                        f"    {sid} -.->|🛡️| {nid}[/\"{nsg_name}\"/]"
                    )

        # Route Table associations
        for vname in members:
            vnet = vnet_map[vname]
            for subnet in vnet.subnets:
                if subnet.route_table_id:
                    rt_name = subnet.route_table_id.split("/")[-1]
                    sid = node_id(f"{vname}_{subnet.name}")
                    rid = node_id(rt_name)
                    lines.append(
                        f"    {sid} -.->|🔀| {rid}[[\"{rt_name}\"]]"
                    )

        # NAT Gateways
        for vname in members:
            vnet = vnet_map[vname]
            for subnet in vnet.subnets:
                if subnet.nat_gateway_id:
                    ng_name = subnet.nat_gateway_id.split("/")[-1]
                    sid = node_id(f"{vname}_{subnet.name}")
                    ngid = node_id(ng_name)
                    ng_pips = pip_by_resource.get(
                        subnet.nat_gateway_id, []
                    )
                    pip_lines = "<br/>".join(
                        f"📌 {ip}" for _, ip in ng_pips
                    )
                    ng_label = ng_name
                    if pip_lines:
                        ng_label = f"{ng_name}<br/>{pip_lines}"
                    lines.append(
                        f"    {ngid}{{\"🌐 {ng_label}\"}}"
                    )
                    lines.append(f"    {sid} -.->|NAT| {ngid}")

        # VPN Gateways that belong to VNets in this group
        group_gw_ids: set[str] = set()
        for gw in topology.vpn_gateways:
            gw_vnet = (
                gw.vnet_id.split("/")[-1] if gw.vnet_id else None
            )
            if gw_vnet not in member_set:
                continue
            group_gw_ids.add(gw.name)
            gid = node_id(gw.name)
            gw_pips = [
                pip_by_id[pid.lower()]
                for pid in gw.public_ips
                if pid.lower() in pip_by_id
            ]
            pip_lines_gw = "<br/>".join(
                f"📌 {ip}" for _, ip in gw_pips
            )
            gw_label = f"{gw.name}<br/>{gw.gateway_type} {gw.sku or ''}"
            if pip_lines_gw:
                gw_label += f"<br/>{pip_lines_gw}"
            lines.append(f"    {gid}([\"🔒 {gw_label}\"])")

            if gw.vnet_id:
                vid = node_id(gw.vnet_id.split("/")[-1])
                lines.append(f"    {vid} --- {gid}")

            for conn in gw.connections:
                if conn.remote_gateway_id:
                    remote_name = conn.remote_gateway_id.split("/")[-1]
                    rid = node_id(remote_name)
                    status = (
                        "🟢" if conn.status == "Connected" else "🔴"
                    )
                    bgp = " BGP" if conn.enable_bgp else ""
                    conn_label = (
                        f"{status} {conn.connection_type}{bgp}"
                    )
                    lines.append(
                        f"    {gid} <-->|{conn_label}| {rid}"
                    )

        # Local Network Gateways referenced by this group's VPN GWs
        lgw_ids: set[str] = set()
        for gw in topology.vpn_gateways:
            if gw.name not in group_gw_ids:
                continue
            for conn in gw.connections:
                if not conn.remote_gateway_id:
                    continue
                remote_name = conn.remote_gateway_id.split("/")[-1]
                rid = node_id(remote_name)
                if rid in lgw_ids:
                    continue
                # Check if it's a discovered local gateway
                lgw_match = next(
                    (lg for lg in topology.local_network_gateways
                     if lg.name == remote_name), None
                )
                if lgw_match:
                    lgw_label = lgw_match.name
                    if lgw_match.gateway_ip:
                        lgw_label += f"<br/>📌 {lgw_match.gateway_ip}"
                    if lgw_match.address_prefixes:
                        pfx = ", ".join(lgw_match.address_prefixes[:3])
                        if len(lgw_match.address_prefixes) > 3:
                            pfx += (
                                f" +{len(lgw_match.address_prefixes) - 3}"
                            )
                        lgw_label += f"<br/>{pfx}"
                    if lgw_match.bgp_asn:
                        lgw_label += f"<br/>BGP ASN {lgw_match.bgp_asn}"
                    lines.append(
                        f"    {rid}([\"🏠 {lgw_label}\"])"
                    )
                else:
                    lines.append(
                        f"    {rid}([\"🏠 {remote_name}\"])"
                    )
                lgw_ids.add(rid)

        # ExpressRoute Circuits linked to this group's VPN/ER gateways
        for er in topology.expressroute_circuits:
            eid = node_id(er.name)
            er_label = er.name
            if er.service_provider:
                er_label += f"<br/>{er.service_provider}"
            if er.bandwidth_mbps:
                er_label += f"<br/>{er.bandwidth_mbps} Mbps"
            peering_names = [p.peering_type for p in er.peerings]
            if peering_names:
                er_label += f"<br/>{', '.join(peering_names)}"
            state = er.service_provider_provisioning_state or "?"
            state_icon = "🟢" if state == "Provisioned" else "🔴"
            er_label += f"<br/>{state_icon} {state}"
            lines.append(f"    {eid}{{{{\"⚡ {er_label}\"}}}}")

        # BGP peers for gateways in this group
        for bp in topology.bgp_peers:
            if bp.gateway_name not in group_gw_ids:
                continue
            bpid = node_id(
                f"bgp_{bp.gateway_name}_{bp.neighbor}"
            )
            state_icon = (
                "🟢" if bp.state == "Connected" else "🔴"
            )
            bp_label = (
                f"{bp.neighbor}<br/>ASN {bp.asn or '?'}<br/>"
                f"{state_icon} {bp.state}<br/>"
                f"{bp.routes_received} routes"
            )
            lines.append(f"    {bpid}([\"🔄 {bp_label}\"])")
            gid = node_id(bp.gateway_name)
            lines.append(f"    {gid} -.->|BGP| {bpid}")

        # vWAN hubs connected to VNets in this group
        for hub in topology.virtual_hubs:
            hub_vnets = [
                c.remote_vnet_name for c in hub.vnet_connections
            ]
            if not any(hv in member_set for hv in hub_vnets):
                continue
            hid = node_id(hub.name)
            hub_label = hub.name
            if hub.address_prefix:
                hub_label += f"<br/>{hub.address_prefix}"
            hub_label += f"<br/>{hub.routing_state}"
            lines.append(f"    {hid}([\"🔵 {hub_label}\"])")

            if hub.virtual_wan_id:
                wan_name = hub.virtual_wan_id.split("/")[-1]
                wid = node_id(wan_name)
                wan = next(
                    (w for w in topology.virtual_wans
                     if w.name == wan_name), None
                )
                if wan:
                    wan_label = f"{wan.name}<br/>{wan.wan_type}"
                    lines.append(
                        f"    {wid}{{{{\"🌍 {wan_label}\"}}}}"
                    )
                lines.append(f"    {wid} --- {hid}")

            for conn in hub.vnet_connections:
                if conn.remote_vnet_name in member_set:
                    vid = node_id(conn.remote_vnet_name)
                    isec = (
                        "🛡️" if conn.enable_internet_security else ""
                    )
                    lines.append(
                        f"    {hid} -->|hub-conn {isec}| {vid}"
                    )

            for gw_id, gw_type in [
                (hub.vpn_gateway_id, "VPN"),
                (hub.er_gateway_id, "ER"),
                (hub.p2s_gateway_id, "P2S"),
            ]:
                if gw_id:
                    gw_name = gw_id.split("/")[-1]
                    gid = node_id(gw_name)
                    lines.append(f"    {hid} ---|{gw_type}| {gid}")

        # Load Balancers in this group
        for lb in topology.load_balancers:
            lb_vnet = None
            for fe in lb.frontends:
                if fe.subnet_id:
                    lb_vnet = subnet_to_vnet.get(fe.subnet_id.lower())
                    break
            if lb.is_internal and lb_vnet not in member_set:
                continue
            if not lb.is_internal:
                # Public LBs: include if any backend is in this group
                # (heuristic — include in first group or standalone)
                # For simplicity, attach to first group if no subnet link
                pass

            lid = node_id(lb.name)
            lb_type = "Internal" if lb.is_internal else "Public"
            lb_label = f"{lb.name}<br/>{lb.sku} {lb_type}"
            if lb.rules:
                ports = ", ".join(
                    str(r.frontend_port) for r in lb.rules[:4]
                )
                if len(lb.rules) > 4:
                    ports += "..."
                lb_label += f"<br/>Ports: {ports}"
            for fe in lb.frontends:
                if (
                    fe.public_ip_id
                    and fe.public_ip_id.lower() in pip_by_id
                ):
                    _, ip = pip_by_id[fe.public_ip_id.lower()]
                    lb_label += f"<br/>📌 {ip}"
                    break
            lines.append(f"    {lid}([\"⚖️ {lb_label}\"])")
            for fe in lb.frontends:
                if fe.subnet_id:
                    sn = fe.subnet_id.split("/subnets/")[-1]
                    vn = (
                        fe.subnet_id.split("/virtualNetworks/")[-1]
                        .split("/")[0]
                    )
                    sid = node_id(f"{vn}_{sn}")
                    lines.append(f"    {sid} --> {lid}")
                    break

        # Application Gateways in this group
        for agw in topology.application_gateways:
            agw_vnet = None
            if agw.subnet_id:
                agw_vnet = subnet_to_vnet.get(agw.subnet_id.lower())
            if agw_vnet not in member_set:
                continue

            aid = node_id(agw.name)
            waf = "WAF ✅" if agw.waf_enabled else "no WAF"
            agw_label = (
                f"{agw.name}<br/>{agw.sku_tier or ''}<br/>{waf}"
            )
            for pip_id in agw.public_ip_ids:
                if pip_id.lower() in pip_by_id:
                    _, ip = pip_by_id[pip_id.lower()]
                    agw_label += f"<br/>📌 {ip}"
                    break
            lines.append(f"    {aid}([\"🔶 {agw_label}\"])")
            if agw.subnet_id:
                sn = agw.subnet_id.split("/subnets/")[-1]
                vn = (
                    agw.subnet_id.split("/virtualNetworks/")[-1]
                    .split("/")[0]
                )
                sid = node_id(f"{vn}_{sn}")
                lines.append(f"    {sid} --> {aid}")

        # Private DNS Zones linked to VNets in this group
        for zone in topology.private_dns_zones:
            linked_vnets = [
                lnk.vnet_name for lnk in zone.vnet_links
                if lnk.vnet_name in member_set
            ]
            if not linked_vnets:
                continue
            zid = node_id(zone.name)
            lines.append(
                f"    {zid}[(\"📛 {zone.name}<br/>"
                f"{zone.record_count} records\")]"
            )
            for link in zone.vnet_links:
                if link.vnet_name in member_set:
                    vid = node_id(link.vnet_name)
                    reg = (
                        "auto-reg"
                        if link.registration_enabled
                        else "resolve"
                    )
                    lines.append(f"    {vid} -.->|{reg}| {zid}")

        # Style classes
        lines.append("")
        lines.append(
            "    classDef vnet fill:#e1f5fe,stroke:#0288d1"
        )
        lines.append(
            "    classDef subnet fill:#f3e5f5,stroke:#7b1fa2"
        )
        lines.append(
            "    classDef nsg fill:#fff3e0,stroke:#f57c00"
        )
        lines.append(
            "    classDef rt fill:#e8f5e9,stroke:#388e3c"
        )

        diagrams.append((title, "\n".join(lines)))

    return diagrams


def generate_mermaid(topology: Topology) -> str:
    """Generate a single Mermaid diagram (backward-compatible wrapper)."""
    diagrams = generate_mermaid_diagrams(topology)
    return "\n\n".join(d for _, d in diagrams)
