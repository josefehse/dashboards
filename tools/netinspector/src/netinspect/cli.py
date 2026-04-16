"""CLI entry point for Network Inspector."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="netinspect",
    help="Azure network topology discovery, documentation, and analysis tool.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def discover(
    subscription: Optional[str] = typer.Option(
        None, "--subscription", "-s",
        help="Azure subscription ID(s), comma-separated for multi-sub",
    ),
    resource_group: Optional[str] = typer.Option(
        None, "--resource-group", "-g", help="Limit to a resource group",
    ),
    vnet: Optional[str] = typer.Option(
        None, "--vnet", "-v",
        help="Start from a specific VNet (requires --resource-group)",
    ),
    follow_peerings: bool = typer.Option(
        True, "--follow-peerings/--no-follow-peerings",
        help="Auto-discover cross-subscription peered VNets",
    ),
    seed: Optional[str] = typer.Option(
        None, "--seed",
        help="Seed VNet name (e.g. hub VNet). Only this VNet and its "
             "connected VNets (peerings, vWAN) will be included in the report.",
    ),
    output: Path = typer.Option(
        "topology.json", "--output", "-o", help="Output JSON file path",
    ),
    report: Optional[Path] = typer.Option(
        None, "--report", "-r", help="Also generate a Markdown report",
    ),
    analyse: bool = typer.Option(
        False, "--analyse/--no-analyse",
        help="Include CAF/WAF analysis findings in the report",
    ),
) -> None:
    """Discover Azure network topology and export it."""
    from azure.mgmt.network import NetworkManagementClient

    from netinspect.auth import (
        extract_subscription_id,
        get_credential,
        resolve_subscriptions,
    )
    from netinspect.discovery.bgp import discover_bgp_peers
    from netinspect.discovery.dns_zones import discover_private_dns_zones
    from netinspect.discovery.expressroute import discover_expressroute_circuits
    from netinspect.discovery.load_balancers import (
        discover_application_gateways,
        discover_load_balancers,
    )
    from netinspect.discovery.local_gateways import discover_local_network_gateways
    from netinspect.discovery.nat_gateways import discover_nat_gateways
    from netinspect.discovery.nsgs import discover_nsgs
    from netinspect.discovery.public_ips import discover_public_ips
    from netinspect.discovery.routes import discover_route_tables
    from netinspect.discovery.vnets import discover_vnets
    from netinspect.discovery.vpn_gateways import discover_vpn_gateways
    from netinspect.discovery.vwan import discover_virtual_wans
    from netinspect.export.json_export import export_json
    from netinspect.export.markdown import export_report
    from netinspect.models.topology import build_topology_graph
    from netinspect.models.types import Topology

    if vnet and not resource_group:
        console.print("[red]--resource-group is required when using --vnet[/red]")
        raise typer.Exit(1)

    # Authenticate
    console.print("\n[bold]🔐 Authenticating...[/bold]")
    credential = get_credential()
    sub_ids = resolve_subscriptions(credential, subscription)

    # Accumulate resources across subscriptions
    all_vnets = []
    all_route_tables = []
    all_nsgs = []
    all_nat_gateways = []
    all_vpn_gateways = []
    all_public_ips = []
    all_private_dns_zones = []
    all_local_gateways = []
    all_er_circuits = []
    all_bgp_peers = []
    all_virtual_wans = []
    all_virtual_hubs = []
    all_load_balancers = []
    all_app_gateways = []
    discovered_sub_ids = set(sub_ids)

    def _discover_subscription(sub_id: str, label: str = "") -> None:
        """Run full discovery for a single subscription."""
        net = NetworkManagementClient(credential, sub_id)
        tag = f" [dim]({label})[/dim]" if label else ""

        console.print(f"\n[bold cyan]── Subscription: {sub_id}{tag} ──[/bold cyan]")

        console.print("[bold]VNets & Subnets:[/bold]")
        all_vnets.extend(discover_vnets(net, resource_group, vnet))

        console.print("\n[bold]Route Tables:[/bold]")
        all_route_tables.extend(discover_route_tables(net))

        console.print("\n[bold]Network Security Groups:[/bold]")
        all_nsgs.extend(discover_nsgs(net))

        console.print("\n[bold]NAT Gateways:[/bold]")
        all_nat_gateways.extend(discover_nat_gateways(net))

        console.print("\n[bold]VPN Gateways:[/bold]")
        gws = discover_vpn_gateways(net)
        all_vpn_gateways.extend(gws)

        console.print("\n[bold]Public IPs:[/bold]")
        all_public_ips.extend(discover_public_ips(net))

        console.print("\n[bold]Private DNS Zones:[/bold]")
        all_private_dns_zones.extend(
            discover_private_dns_zones(credential, sub_id)
        )

        console.print("\n[bold]Local Network Gateways:[/bold]")
        all_local_gateways.extend(discover_local_network_gateways(net))

        console.print("\n[bold]ExpressRoute Circuits:[/bold]")
        all_er_circuits.extend(discover_expressroute_circuits(net))

        console.print("\n[bold]BGP Peers:[/bold]")
        all_bgp_peers.extend(discover_bgp_peers(net, gws))

        console.print("\n[bold]Virtual WAN:[/bold]")
        wans, hubs = discover_virtual_wans(net)
        all_virtual_wans.extend(wans)
        all_virtual_hubs.extend(hubs)

        console.print("\n[bold]Load Balancers:[/bold]")
        all_load_balancers.extend(discover_load_balancers(net))

        console.print("\n[bold]Application Gateways:[/bold]")
        all_app_gateways.extend(discover_application_gateways(net))

    # Discover each requested subscription
    console.print("\n[bold]🔍 Discovering network topology...[/bold]")
    for sid in sub_ids:
        _discover_subscription(sid)

    # Auto-follow cross-subscription peerings
    if follow_peerings:
        cross_sub_ids: set[str] = set()
        for v in all_vnets:
            for p in v.peerings:
                remote_sub = extract_subscription_id(p.remote_vnet_id)
                if remote_sub and remote_sub not in discovered_sub_ids:
                    cross_sub_ids.add(remote_sub)

        if cross_sub_ids:
            console.print(
                f"\n[bold yellow]🔗 Found cross-subscription peerings to "
                f"{len(cross_sub_ids)} additional subscription(s) — "
                f"auto-discovering...[/bold yellow]"
            )
            for xsub in cross_sub_ids:
                try:
                    _discover_subscription(xsub, label="auto-followed")
                    discovered_sub_ids.add(xsub)
                except Exception as exc:
                    console.print(
                        f"  [yellow]⚠ Could not discover subscription "
                        f"{xsub}: {exc}[/yellow]"
                    )

    # Build topology
    topology = Topology(
        subscription_ids=sorted(discovered_sub_ids),
        subscription_id=sub_ids[0],
        vnets=all_vnets,
        route_tables=all_route_tables,
        nsgs=all_nsgs,
        nat_gateways=all_nat_gateways,
        vpn_gateways=all_vpn_gateways,
        public_ips=all_public_ips,
        private_dns_zones=all_private_dns_zones,
        local_network_gateways=all_local_gateways,
        expressroute_circuits=all_er_circuits,
        bgp_peers=all_bgp_peers,
        virtual_wans=all_virtual_wans,
        virtual_hubs=all_virtual_hubs,
        load_balancers=all_load_balancers,
        application_gateways=all_app_gateways,
    )

    # Seed-filter: keep only the seed VNet and its connected neighbours
    if seed:
        topology = _filter_topology_by_seed(topology, seed, console)

    # Build graph and show summary
    topo_graph = build_topology_graph(topology)
    summary = topo_graph.summary()

    console.print("\n[bold]📊 Topology Summary:[/bold]")
    console.print(f"  Subscriptions: {len(discovered_sub_ids)}")
    node_str = ", ".join(f"{v} {k}s" for k, v in summary["node_types"].items())
    edge_str = ", ".join(f"{v} {k}" for k, v in summary["edge_types"].items())
    console.print(f"  Nodes: {summary['total_nodes']} ({node_str})")
    console.print(f"  Edges: {summary['total_edges']} ({edge_str})")

    # Export JSON
    export_json(topology, output)
    console.print(f"\n[green]✅ JSON snapshot saved to:[/green] {output}")

    # Export report if requested
    if report:
        export_report(topology, report, include_analysis=analyse)
        console.print(f"[green]✅ Markdown report saved to:[/green] {report}")


def _filter_topology_by_seed(
    topology: "Topology", seed_name: str, console: Console,
) -> "Topology":
    """Return a new Topology containing only VNets reachable from *seed_name*.

    Reachability is determined by VNet peerings and vWAN hub connections.
    All non-VNet resources (route tables, NSGs, gateways, …) are filtered to
    only those referenced by the remaining VNets.
    """
    from netinspect.models.types import Topology

    vnet_map = {v.name.lower(): v for v in topology.vnets}
    if seed_name.lower() not in vnet_map:
        console.print(
            f"[red]Seed VNet '{seed_name}' not found in discovered VNets.[/red]"
        )
        raise SystemExit(1)

    # BFS / flood-fill from the seed
    reachable: set[str] = set()
    queue: list[str] = [seed_name.lower()]

    # Pre-build vWAN adjacency: vnet -> set of peer vnet names via hubs
    hub_adj: dict[str, set[str]] = {}
    for hub in topology.virtual_hubs:
        hub_vnets = [
            c.remote_vnet_name.lower() for c in hub.vnet_connections
            if c.remote_vnet_name.lower() in vnet_map
        ]
        for vn in hub_vnets:
            hub_adj.setdefault(vn, set()).update(hub_vnets)

    while queue:
        current = queue.pop()
        if current in reachable:
            continue
        reachable.add(current)
        vnet = vnet_map.get(current)
        if not vnet:
            continue
        # Follow peerings
        for p in vnet.peerings:
            peer = p.remote_vnet_name.lower()
            if peer in vnet_map and peer not in reachable:
                queue.append(peer)
        # Follow vWAN hub connections
        for peer in hub_adj.get(current, set()):
            if peer not in reachable:
                queue.append(peer)

    filtered_vnets = [v for v in topology.vnets if v.name.lower() in reachable]
    vnet_ids_lower = {v.id.lower() for v in filtered_vnets}

    console.print(
        f"\n[bold]🌱 Seed filter:[/bold] keeping "
        f"[cyan]{len(filtered_vnets)}[/cyan] VNet(s) reachable from "
        f"[bold]{seed_name}[/bold]"
    )

    # Helper to check if a resource ID references one of the kept VNets
    def _vnet_id_match(rid: str | None) -> bool:
        if not rid:
            return False
        return rid.lower() in vnet_ids_lower

    # Collect all resource IDs referenced by kept VNets' subnets
    kept_nsg_ids = set()
    kept_rt_ids = set()
    kept_nat_ids = set()
    for v in filtered_vnets:
        for s in v.subnets:
            if s.nsg_id:
                kept_nsg_ids.add(s.nsg_id.lower())
            if s.route_table_id:
                kept_rt_ids.add(s.route_table_id.lower())
            if s.nat_gateway_id:
                kept_nat_ids.add(s.nat_gateway_id.lower())

    # Filter VPN gateways to those attached to kept VNets
    filtered_gws = [
        gw for gw in topology.vpn_gateways if _vnet_id_match(gw.vnet_id)
    ]
    gw_names = {gw.name for gw in filtered_gws}

    # Filter vWAN hubs that connect to any kept VNet
    filtered_hubs = [
        h for h in topology.virtual_hubs
        if any(c.remote_vnet_name.lower() in reachable for c in h.vnet_connections)
    ]
    hub_wan_ids = {h.virtual_wan_id for h in filtered_hubs if h.virtual_wan_id}
    filtered_wans = [
        w for w in topology.virtual_wans if w.id in hub_wan_ids
    ]

    return Topology(
        subscription_ids=topology.subscription_ids,
        subscription_id=topology.subscription_id,
        vnets=filtered_vnets,
        route_tables=[rt for rt in topology.route_tables if rt.id and rt.id.lower() in kept_rt_ids],
        nsgs=[n for n in topology.nsgs if n.id and n.id.lower() in kept_nsg_ids],
        nat_gateways=[ng for ng in topology.nat_gateways if ng.id and ng.id.lower() in kept_nat_ids],
        vpn_gateways=filtered_gws,
        public_ips=topology.public_ips,  # keep all; lightweight
        private_dns_zones=topology.private_dns_zones,
        local_network_gateways=topology.local_network_gateways,
        expressroute_circuits=topology.expressroute_circuits,
        bgp_peers=[bp for bp in topology.bgp_peers if bp.gateway_name in gw_names],
        virtual_wans=filtered_wans,
        virtual_hubs=filtered_hubs,
        load_balancers=topology.load_balancers,
        application_gateways=topology.application_gateways,
    )


@app.command()
def query(
    input: Path = typer.Option(
        "topology.json", "--input", "-i", help="Input JSON topology file",
    ),
    source: str = typer.Option(
        ..., "--from", "-f",
        help="Source subnet (vnet/subnet name or subnet ID)",
    ),
    dest: str = typer.Option(
        ..., "--to", "-t", help="Destination IP address",
    ),
    port: int = typer.Option(
        443, "--port", "-p", help="Destination port",
    ),
    protocol: str = typer.Option(
        "TCP", "--protocol", help="Protocol (TCP, UDP, ICMP, *)",
    ),
) -> None:
    """Check if traffic can reach from a source subnet to a destination."""
    from netinspect.analysis.reachability import check_reachability
    from netinspect.export.json_export import load_json

    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    data = load_json(input)
    topology = _topology_from_dict(data)

    # Resolve source subnet
    subnet_id = _resolve_subnet(topology, source)
    if not subnet_id:
        console.print(f"[red]Subnet not found: {source}[/red]")
        console.print("\n[bold]Available subnets:[/bold]")
        for v in topology.vnets:
            for s in v.subnets:
                console.print(f"  {v.name}/{s.name}  ({s.address_prefix})")
        raise typer.Exit(1)

    result = check_reachability(
        topology, subnet_id, dest, port, protocol,
    )

    console.print("\n[bold]🔎 Reachability Analysis[/bold]\n")
    for step in result.steps:
        console.print(f"  {step}")

    console.print()
    if result.reachable:
        console.print("[bold green]Result: REACHABLE ✅[/bold green]")
    else:
        console.print("[bold red]Result: NOT REACHABLE ❌[/bold red]")


@app.command()
def routes(
    input: Path = typer.Option(
        "topology.json", "--input", "-i", help="Input JSON topology file",
    ),
    subnet: Optional[str] = typer.Option(
        None, "--subnet", "-s",
        help="Filter to a specific subnet (vnet/subnet name)",
    ),
) -> None:
    """Show effective routes for all subnets (or a specific one)."""
    from rich.table import Table

    from netinspect.analysis.routing import compute_effective_routes
    from netinspect.export.json_export import load_json

    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    data = load_json(input)
    topology = _topology_from_dict(data)

    all_routes = compute_effective_routes(topology)

    for info in all_routes:
        full_name = f"{info.vnet_name}/{info.subnet_name}"
        if subnet and subnet.lower() not in full_name.lower():
            continue

        nat_info = f" 🌐 NAT: {info.nat_gateway_name}" if info.has_nat_gateway else ""
        console.print(
            f"\n[bold]📋 {full_name}[/bold] ({info.subnet_prefix}){nat_info}"
        )

        table = Table(show_header=True, header_style="bold")
        table.add_column("Source", style="dim")
        table.add_column("Prefix")
        table.add_column("Next Hop Type")
        table.add_column("Next Hop IP")
        table.add_column("Detail")
        table.add_column("Active")

        for r in info.routes:
            active = "✅" if r.active else "⬜"
            table.add_row(
                r.source,
                r.address_prefix,
                r.next_hop_type,
                r.next_hop_ip or "—",
                r.next_hop_detail or "—",
                active,
            )

        console.print(table)


@app.command()
def analyze(
    input: Path = typer.Option(
        "topology.json", "--input", "-i",
        help="Input JSON topology file",
    ),
    category: Optional[str] = typer.Option(
        None, "--category", "-c",
        help="Filter by category (Security, Reliability, Cost, Design)",
    ),
    severity: Optional[str] = typer.Option(
        None, "--severity",
        help="Minimum severity (Critical, Warning, Info)",
    ),
) -> None:
    """Analyze topology against CAF/WAF best practices."""
    from rich.panel import Panel
    from rich.table import Table

    from netinspect.analysis.analyze import analyze_topology
    from netinspect.analysis.findings import Category, Severity
    from netinspect.export.json_export import load_json

    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    data = load_json(input)
    topology = _topology_from_dict(data)

    console.print("\n[bold]🔍 Analyzing topology against CAF/WAF...[/bold]\n")
    report = analyze_topology(topology)

    findings = report.sorted_findings()

    # Filter by category
    if category:
        try:
            cat = Category(category)
        except ValueError:
            cat = next(
                (c for c in Category if c.value.lower().startswith(
                    category.lower()
                )), None,
            )
        if cat:
            findings = [f for f in findings if f.category == cat]

    # Filter by severity
    if severity:
        sev_order = {
            Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2,
        }
        try:
            min_sev = Severity(severity)
        except ValueError:
            min_sev = next(
                (s for s in Severity if s.value.lower().startswith(
                    severity.lower()
                )), Severity.INFO,
            )
        max_order = sev_order[min_sev]
        findings = [
            f for f in findings if sev_order[f.severity] <= max_order
        ]

    if not findings:
        console.print("[green]✅ No findings![/green]")
        return

    # Summary panel
    console.print(Panel(
        f"[red bold]{report.critical_count} Critical[/red bold]  "
        f"[yellow bold]{report.warning_count} Warning[/yellow bold]  "
        f"[blue]{report.info_count} Info[/blue]  "
        f"— [bold]{len(report.findings)} total findings[/bold]",
        title="📊 Analysis Summary",
    ))

    # Findings table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Sev", width=3)
    table.add_column("Category", width=18)
    table.add_column("Finding")
    table.add_column("Resource", style="dim")
    table.add_column("Recommendation", max_width=40)

    for f in findings:
        sev_style = {
            Severity.CRITICAL: "bold red",
            Severity.WARNING: "yellow",
            Severity.INFO: "blue",
        }[f.severity]
        table.add_row(
            f.severity_icon,
            f.category.value,
            f"[{sev_style}]{f.title}[/{sev_style}]",
            f.resource_name or "—",
            f.recommendation[:80],
        )

    console.print(table)


@app.command()
def report(
    input: Path = typer.Option("topology.json", "--input", "-i", help="Input JSON topology file"),
    output: Path = typer.Option("report.md", "--output", "-o", help="Output Markdown report file"),
    analyse: bool = typer.Option(
        False, "--analyse/--no-analyse",
        help="Include CAF/WAF analysis findings in the report",
    ),
) -> None:
    """Generate a Markdown report from a previously saved topology snapshot."""

    from netinspect.export.json_export import load_json
    from netinspect.export.markdown import export_report as write_report

    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]📄 Loading topology from:[/bold] {input}")
    data = load_json(input)

    # Reconstruct Topology from dict
    topology = _topology_from_dict(data)

    write_report(topology, output, include_analysis=analyse)
    console.print(f"[green]✅ Markdown report saved to:[/green] {output}")


@app.command()
def show(
    input: Path = typer.Option("topology.json", "--input", "-i", help="Input JSON topology file"),
) -> None:
    """Display a quick summary of a saved topology."""
    from netinspect.export.json_export import load_json

    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    data = load_json(input)
    topology = _topology_from_dict(data)

    from netinspect.models.topology import build_topology_graph

    topo_graph = build_topology_graph(topology)
    summary = topo_graph.summary()

    sub_ids = topology.subscription_ids or [topology.subscription_id]
    sub_str = ", ".join(sub_ids) if sub_ids else "unknown"
    console.print(f"\n[bold]📊 Topology Summary[/bold] ({len(sub_ids)} subscription(s): {sub_str})")
    console.print(f"  VNets:        {len(topology.vnets)}")
    console.print(f"  Route Tables: {len(topology.route_tables)}")
    console.print(f"  NSGs:         {len(topology.nsgs)}")
    console.print(f"  NAT Gateways: {len(topology.nat_gateways)}")
    console.print(f"  VPN Gateways: {len(topology.vpn_gateways)}")
    console.print(f"  Public IPs:   {len(topology.public_ips)}")
    console.print(f"  DNS Zones:    {len(topology.private_dns_zones)}")
    console.print(f"  Local GWs:    {len(topology.local_network_gateways)}")
    console.print(f"  ER Circuits:  {len(topology.expressroute_circuits)}")
    console.print(f"  BGP Peers:    {len(topology.bgp_peers)}")
    console.print(f"  vWANs:        {len(topology.virtual_wans)}")
    console.print(f"  vHubs:        {len(topology.virtual_hubs)}")
    console.print(f"  Load Balancers: {len(topology.load_balancers)}")
    console.print(f"  App Gateways: {len(topology.application_gateways)}")
    console.print(f"  Graph nodes:  {summary['total_nodes']}")
    console.print(f"  Graph edges:  {summary['total_edges']}")

    if topology.vnets:
        console.print("\n[bold]VNets:[/bold]")
        for v in topology.vnets:
            addr = ", ".join(v.address_spaces)
            n_sub = len(v.subnets)
            n_peer = len(v.peerings)
            console.print(
                f"  • {v.name} ({v.location}) — {addr}"
                f" — {n_sub} subnets, {n_peer} peerings"
            )


def _topology_from_dict(data: dict):  # -> Topology
    """Reconstruct a Topology from a JSON-loaded dict."""
    from netinspect.models.types import (
        NSG,
        AppGatewayBackendPool,
        AppGatewayListener,
        AppGatewayRoutingRule,
        ApplicationGateway,
        BgpPeerStatus,
        ExpressRouteCircuit,
        ExpressRoutePeering,
        HubRouteTable,
        HubVnetConnection,
        LoadBalancer,
        LoadBalancerBackendPool,
        LoadBalancerFrontend,
        LoadBalancerProbe,
        LoadBalancerRule,
        LocalNetworkGateway,
        NatGateway,
        Peering,
        PeeringState,
        PrivateDnsVnetLink,
        PrivateDnsZone,
        PublicIP,
        Route,
        RouteTable,
        SecurityRule,
        SecurityRuleAccess,
        SecurityRuleDirection,
        Subnet,
        Topology,
        VirtualHub,
        VirtualWan,
        VNet,
        VpnGateway,
        VpnGatewayConnection,
    )

    vnets = []
    for v in data.get("vnets", []):
        subnets = [Subnet(**s) for s in v.get("subnets", [])]
        peerings = []
        for p in v.get("peerings", []):
            p["state"] = PeeringState(p["state"])
            peerings.append(Peering(**p))
        vnets.append(VNet(
            id=v["id"], name=v["name"], resource_group=v["resource_group"],
            location=v["location"], address_spaces=v.get("address_spaces", []),
            dns_servers=v.get("dns_servers", []), subnets=subnets, peerings=peerings,
            tags=v.get("tags", {}),
        ))

    route_tables = []
    for rt in data.get("route_tables", []):
        routes = [Route(**r) for r in rt.get("routes", [])]
        route_tables.append(RouteTable(
            id=rt["id"], name=rt["name"], resource_group=rt["resource_group"],
            location=rt["location"], routes=routes,
            associated_subnets=rt.get("associated_subnets", []),
            disable_bgp_route_propagation=rt.get("disable_bgp_route_propagation", False),
            tags=rt.get("tags", {}),
        ))

    nsgs = []
    for n in data.get("nsgs", []):
        rules = []
        for r in n.get("rules", []):
            r["direction"] = SecurityRuleDirection(r["direction"])
            r["access"] = SecurityRuleAccess(r["access"])
            rules.append(SecurityRule(**r))
        nsgs.append(NSG(
            id=n["id"], name=n["name"], resource_group=n["resource_group"],
            location=n["location"], rules=rules,
            associated_subnets=n.get("associated_subnets", []),
            associated_nics=n.get("associated_nics", []),
            tags=n.get("tags", {}),
        ))

    nat_gateways = []
    for ng in data.get("nat_gateways", []):
        nat_gateways.append(NatGateway(
            id=ng["id"], name=ng["name"],
            resource_group=ng["resource_group"],
            location=ng["location"],
            sku=ng.get("sku", "Standard"),
            idle_timeout_minutes=ng.get("idle_timeout_minutes", 4),
            public_ip_addresses=ng.get("public_ip_addresses", []),
            public_ip_prefixes=ng.get("public_ip_prefixes", []),
            associated_subnets=ng.get("associated_subnets", []),
            tags=ng.get("tags", {}),
        ))

    vpn_gateways = []
    for gw in data.get("vpn_gateways", []):
        conns = []
        for c in gw.get("connections", []):
            conns.append(VpnGatewayConnection(**c))
        vpn_gateways.append(VpnGateway(
            id=gw["id"], name=gw["name"],
            resource_group=gw["resource_group"],
            location=gw["location"],
            gateway_type=gw.get("gateway_type", ""),
            vpn_type=gw.get("vpn_type"),
            sku=gw.get("sku"),
            vnet_id=gw.get("vnet_id"),
            bgp_enabled=gw.get("bgp_enabled", False),
            bgp_asn=gw.get("bgp_asn"),
            bgp_peering_address=gw.get("bgp_peering_address"),
            active_active=gw.get("active_active", False),
            public_ips=gw.get("public_ips", []),
            connections=conns,
            tags=gw.get("tags", {}),
        ))

    return Topology(
        subscription_ids=data.get("subscription_ids", []),
        subscription_id=data.get("subscription_id", ""),
        vnets=vnets, route_tables=route_tables, nsgs=nsgs,
        nat_gateways=nat_gateways, vpn_gateways=vpn_gateways,
        public_ips=[PublicIP(**p) for p in data.get("public_ips", [])],
        private_dns_zones=[
            PrivateDnsZone(
                id=z["id"], name=z["name"],
                resource_group=z["resource_group"],
                record_count=z.get("record_count", 0),
                vnet_links=[
                    PrivateDnsVnetLink(**lnk)
                    for lnk in z.get("vnet_links", [])
                ],
                tags=z.get("tags", {}),
            )
            for z in data.get("private_dns_zones", [])
        ],
        local_network_gateways=[
            LocalNetworkGateway(**lgw)
            for lgw in data.get("local_network_gateways", [])
        ],
        expressroute_circuits=[
            ExpressRouteCircuit(
                id=er["id"], name=er["name"],
                resource_group=er["resource_group"],
                location=er["location"],
                service_provider=er.get("service_provider"),
                peering_location=er.get("peering_location"),
                bandwidth_mbps=er.get("bandwidth_mbps"),
                sku_tier=er.get("sku_tier"),
                sku_family=er.get("sku_family"),
                circuit_provisioning_state=er.get(
                    "circuit_provisioning_state"
                ),
                service_provider_provisioning_state=er.get(
                    "service_provider_provisioning_state"
                ),
                peerings=[
                    ExpressRoutePeering(**p)
                    for p in er.get("peerings", [])
                ],
                gateway_connections=er.get("gateway_connections", []),
                tags=er.get("tags", {}),
            )
            for er in data.get("expressroute_circuits", [])
        ],
        bgp_peers=[
            BgpPeerStatus(**bp)
            for bp in data.get("bgp_peers", [])
        ],
        virtual_wans=[
            VirtualWan(**w)
            for w in data.get("virtual_wans", [])
        ],
        virtual_hubs=[
            VirtualHub(
                id=h["id"], name=h["name"],
                resource_group=h["resource_group"],
                location=h["location"],
                virtual_wan_id=h.get("virtual_wan_id"),
                address_prefix=h.get("address_prefix"),
                sku=h.get("sku"),
                provisioning_state=h.get("provisioning_state", ""),
                routing_state=h.get("routing_state", ""),
                vnet_connections=[
                    HubVnetConnection(**c)
                    for c in h.get("vnet_connections", [])
                ],
                route_tables=[
                    HubRouteTable(**rt)
                    for rt in h.get("route_tables", [])
                ],
                vpn_gateway_id=h.get("vpn_gateway_id"),
                er_gateway_id=h.get("er_gateway_id"),
                p2s_gateway_id=h.get("p2s_gateway_id"),
                tags=h.get("tags", {}),
            )
            for h in data.get("virtual_hubs", [])
        ],
        load_balancers=[
            LoadBalancer(
                id=lb["id"], name=lb["name"],
                resource_group=lb["resource_group"],
                location=lb["location"],
                sku=lb.get("sku", "Standard"),
                is_internal=lb.get("is_internal", False),
                frontends=[
                    LoadBalancerFrontend(**fe)
                    for fe in lb.get("frontends", [])
                ],
                backend_pools=[
                    LoadBalancerBackendPool(**bp)
                    for bp in lb.get("backend_pools", [])
                ],
                rules=[
                    LoadBalancerRule(**r)
                    for r in lb.get("rules", [])
                ],
                probes=[
                    LoadBalancerProbe(**p)
                    for p in lb.get("probes", [])
                ],
                tags=lb.get("tags", {}),
            )
            for lb in data.get("load_balancers", [])
        ],
        application_gateways=[
            ApplicationGateway(
                id=agw["id"], name=agw["name"],
                resource_group=agw["resource_group"],
                location=agw["location"],
                sku_name=agw.get("sku_name"),
                sku_tier=agw.get("sku_tier"),
                capacity=agw.get("capacity"),
                waf_enabled=agw.get("waf_enabled", False),
                waf_mode=agw.get("waf_mode"),
                subnet_id=agw.get("subnet_id"),
                listeners=[
                    AppGatewayListener(**lis)
                    for lis in agw.get("listeners", [])
                ],
                backend_pools=[
                    AppGatewayBackendPool(**bp)
                    for bp in agw.get("backend_pools", [])
                ],
                routing_rules=[
                    AppGatewayRoutingRule(**r)
                    for r in agw.get("routing_rules", [])
                ],
                public_ip_ids=agw.get("public_ip_ids", []),
                tags=agw.get("tags", {}),
            )
            for agw in data.get("application_gateways", [])
        ],
    )


def _resolve_subnet(topology, name: str) -> str | None:
    """Resolve a subnet name like 'vnet-hub/default' to a subnet ID.

    Also accepts a raw Azure resource ID.
    """
    if "/subnets/" in name.lower() or name.startswith("/"):
        # Already a resource ID — verify it exists
        for v in topology.vnets:
            for s in v.subnets:
                if s.id.lower() == name.lower():
                    return s.id
        return None

    # Try "vnet/subnet" format
    parts = name.split("/", 1)
    if len(parts) == 2:
        vnet_name, subnet_name = parts
        for v in topology.vnets:
            if v.name.lower() == vnet_name.lower():
                for s in v.subnets:
                    if s.name.lower() == subnet_name.lower():
                        return s.id

    # Try just subnet name (return first match)
    for v in topology.vnets:
        for s in v.subnets:
            if s.name.lower() == name.lower():
                return s.id

    return None
