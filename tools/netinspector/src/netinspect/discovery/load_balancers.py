"""Discover Load Balancers and Application Gateways."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import (
    AppGatewayBackendPool,
    AppGatewayListener,
    AppGatewayRoutingRule,
    ApplicationGateway,
    LoadBalancer,
    LoadBalancerBackendPool,
    LoadBalancerFrontend,
    LoadBalancerProbe,
    LoadBalancerRule,
)

console = Console()


def discover_load_balancers(
    network_client: NetworkManagementClient,
) -> list[LoadBalancer]:
    """Discover all Load Balancers in the subscription."""
    lbs = []
    try:
        for raw in network_client.load_balancers.list_all():
            lb = _parse_load_balancer(raw)
            lbs.append(lb)

            lb_type = "Internal" if lb.is_internal else "Public"
            console.print(
                f"  Discovered LB: [cyan]{lb.name}[/cyan] "
                f"({lb_type}, {lb.sku}, "
                f"{len(lb.frontends)} frontends, "
                f"{len(lb.backend_pools)} pools, "
                f"{len(lb.rules)} rules)"
            )
    except Exception as e:
        console.print(
            f"  [yellow]Could not list load balancers: {e}[/yellow]"
        )

    if not lbs:
        console.print("  [dim]No load balancers found.[/dim]")

    return lbs


def discover_application_gateways(
    network_client: NetworkManagementClient,
) -> list[ApplicationGateway]:
    """Discover all Application Gateways in the subscription."""
    appgws = []
    try:
        for raw in network_client.application_gateways.list_all():
            agw = _parse_app_gateway(raw)
            appgws.append(agw)

            waf = f"WAF {agw.waf_mode}" if agw.waf_enabled else "no WAF"
            console.print(
                f"  Discovered AppGW: [cyan]{agw.name}[/cyan] "
                f"({agw.sku_tier}, {waf}, "
                f"{len(agw.listeners)} listeners, "
                f"{len(agw.backend_pools)} pools)"
            )
    except Exception as e:
        console.print(
            f"  [yellow]Could not list application gateways: "
            f"{e}[/yellow]"
        )

    if not appgws:
        console.print("  [dim]No application gateways found.[/dim]")

    return appgws


def _parse_load_balancer(raw) -> LoadBalancer:
    """Parse a Load Balancer SDK object."""
    rg = _extract_resource_group(raw.id)

    frontends = []
    is_internal = True
    for fe in raw.frontend_ip_configurations or []:
        pip_id = None
        if fe.public_ip_address:
            pip_id = fe.public_ip_address.id
            is_internal = False
        frontends.append(LoadBalancerFrontend(
            name=fe.name or "",
            private_ip=fe.private_ip_address,
            public_ip_id=pip_id,
            subnet_id=fe.subnet.id if fe.subnet else None,
        ))

    backend_pools = []
    for bp in raw.backend_address_pools or []:
        ip_count = len(bp.backend_ip_configurations or [])
        # Also count load_balancer_backend_addresses
        if hasattr(bp, "load_balancer_backend_addresses"):
            addr_list = bp.load_balancer_backend_addresses or []
            ip_count = max(ip_count, len(addr_list))
        backend_pools.append(LoadBalancerBackendPool(
            name=bp.name or "",
            ip_count=ip_count,
        ))

    rules = []
    for r in raw.load_balancing_rules or []:
        fe_name = ""
        if r.frontend_ip_configuration:
            fe_name = (r.frontend_ip_configuration.id or "").split("/")[-1]
        bp_name = ""
        if r.backend_address_pool:
            bp_name = (r.backend_address_pool.id or "").split("/")[-1]
        probe_name = ""
        if r.probe:
            probe_name = (r.probe.id or "").split("/")[-1]
        rules.append(LoadBalancerRule(
            name=r.name or "",
            frontend_port=r.frontend_port or 0,
            backend_port=r.backend_port or 0,
            protocol=r.protocol or "",
            frontend_name=fe_name,
            backend_pool_name=bp_name,
            probe_name=probe_name,
        ))

    probes = []
    for p in raw.probes or []:
        probes.append(LoadBalancerProbe(
            name=p.name or "",
            protocol=p.protocol or "",
            port=p.port or 0,
            interval=p.interval_in_seconds or 15,
            path=p.request_path,
        ))

    return LoadBalancer(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        sku=raw.sku.name if raw.sku else "Basic",
        is_internal=is_internal,
        frontends=frontends,
        backend_pools=backend_pools,
        rules=rules,
        probes=probes,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _parse_app_gateway(raw) -> ApplicationGateway:
    """Parse an Application Gateway SDK object."""
    rg = _extract_resource_group(raw.id)

    # SKU
    sku_name = raw.sku.name if raw.sku else None
    sku_tier = raw.sku.tier if raw.sku else None
    capacity = raw.sku.capacity if raw.sku else None

    # WAF
    waf_enabled = False
    waf_mode = None
    if raw.web_application_firewall_configuration:
        waf_enabled = (
            raw.web_application_firewall_configuration.enabled or False
        )
        waf_mode = (
            raw.web_application_firewall_configuration.firewall_mode
        )
    # Also check firewall_policy
    if raw.firewall_policy:
        waf_enabled = True

    # Subnet
    subnet_id = None
    for gic in raw.gateway_ip_configurations or []:
        if gic.subnet:
            subnet_id = gic.subnet.id
            break

    # Public IPs from frontend configs
    public_ip_ids = []
    for fe in raw.frontend_ip_configurations or []:
        if fe.public_ip_address:
            public_ip_ids.append(fe.public_ip_address.id)

    # Listeners
    listeners = []
    for lis in raw.http_listeners or []:
        fe_name = ""
        if lis.frontend_ip_configuration:
            fe_name = (lis.frontend_ip_configuration.id or "").split("/")[-1]
        listeners.append(AppGatewayListener(
            name=lis.name or "",
            frontend_ip_name=fe_name,
            port=lis.frontend_port.id.split("/")[-1] if lis.frontend_port else 0,
            protocol=lis.protocol or "",
            host_name=lis.host_name,
        ))

    # Backend pools
    backend_pools = []
    for bp in raw.backend_address_pools or []:
        targets = len(bp.backend_addresses or [])
        backend_pools.append(AppGatewayBackendPool(
            name=bp.name or "",
            target_count=targets,
        ))

    # Routing rules
    routing_rules = []
    for r in raw.request_routing_rules or []:
        listener_name = ""
        if r.http_listener:
            listener_name = (r.http_listener.id or "").split("/")[-1]
        bp_name = ""
        if r.backend_address_pool:
            bp_name = (r.backend_address_pool.id or "").split("/")[-1]
        routing_rules.append(AppGatewayRoutingRule(
            name=r.name or "",
            rule_type=r.rule_type or "",
            listener_name=listener_name,
            backend_pool_name=bp_name,
            priority=r.priority,
        ))

    return ApplicationGateway(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        sku_name=sku_name,
        sku_tier=sku_tier,
        capacity=capacity,
        waf_enabled=waf_enabled,
        waf_mode=waf_mode,
        subnet_id=subnet_id,
        listeners=listeners,
        backend_pools=backend_pools,
        routing_rules=routing_rules,
        public_ip_ids=public_ip_ids,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
