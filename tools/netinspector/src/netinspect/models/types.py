"""Data types for Azure network topology objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PeeringState(str, Enum):
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    INITIATED = "Initiated"


class SecurityRuleAccess(str, Enum):
    ALLOW = "Allow"
    DENY = "Deny"


class SecurityRuleDirection(str, Enum):
    INBOUND = "Inbound"
    OUTBOUND = "Outbound"


class RouteNextHopType(str, Enum):
    VIRTUAL_NETWORK_GATEWAY = "VirtualNetworkGateway"
    VNET_LOCAL = "VnetLocal"
    INTERNET = "Internet"
    VIRTUAL_APPLIANCE = "VirtualAppliance"
    NONE = "None"


@dataclass
class Subnet:
    id: str
    name: str
    address_prefix: str
    nsg_id: str | None = None
    route_table_id: str | None = None
    nat_gateway_id: str | None = None
    delegations: list[str] = field(default_factory=list)
    service_endpoints: list[str] = field(default_factory=list)


@dataclass
class Peering:
    id: str
    name: str
    remote_vnet_id: str
    remote_vnet_name: str
    state: PeeringState
    allow_virtual_network_access: bool = True
    allow_forwarded_traffic: bool = False
    allow_gateway_transit: bool = False
    use_remote_gateways: bool = False


@dataclass
class VNet:
    id: str
    name: str
    resource_group: str
    location: str
    address_spaces: list[str] = field(default_factory=list)
    dns_servers: list[str] = field(default_factory=list)
    subnets: list[Subnet] = field(default_factory=list)
    peerings: list[Peering] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class Route:
    name: str
    address_prefix: str
    next_hop_type: str
    next_hop_ip: str | None = None


@dataclass
class RouteTable:
    id: str
    name: str
    resource_group: str
    location: str
    routes: list[Route] = field(default_factory=list)
    associated_subnets: list[str] = field(default_factory=list)
    disable_bgp_route_propagation: bool = False
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class SecurityRule:
    name: str
    priority: int
    direction: SecurityRuleDirection
    access: SecurityRuleAccess
    protocol: str
    source_address_prefix: str | None = None
    source_address_prefixes: list[str] = field(default_factory=list)
    source_port_range: str | None = None
    destination_address_prefix: str | None = None
    destination_address_prefixes: list[str] = field(default_factory=list)
    destination_port_range: str | None = None
    description: str | None = None


@dataclass
class NSG:
    id: str
    name: str
    resource_group: str
    location: str
    rules: list[SecurityRule] = field(default_factory=list)
    associated_subnets: list[str] = field(default_factory=list)
    associated_nics: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class NatGateway:
    id: str
    name: str
    resource_group: str
    location: str
    sku: str = "Standard"
    idle_timeout_minutes: int = 4
    public_ip_addresses: list[str] = field(default_factory=list)
    public_ip_prefixes: list[str] = field(default_factory=list)
    associated_subnets: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class VpnGatewayConnection:
    id: str
    name: str
    connection_type: str
    status: str
    remote_gateway_id: str | None = None
    shared_key_set: bool = False
    enable_bgp: bool = False


@dataclass
class VpnGateway:
    id: str
    name: str
    resource_group: str
    location: str
    gateway_type: str  # Vpn or ExpressRoute
    vpn_type: str | None = None  # RouteBased or PolicyBased
    sku: str | None = None
    vnet_id: str | None = None
    bgp_enabled: bool = False
    bgp_asn: int | None = None
    bgp_peering_address: str | None = None
    active_active: bool = False
    public_ips: list[str] = field(default_factory=list)
    connections: list[VpnGatewayConnection] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class PublicIP:
    id: str
    name: str
    resource_group: str
    location: str
    ip_address: str | None = None
    allocation_method: str = "Static"  # Static or Dynamic
    sku: str = "Standard"
    associated_resource_id: str | None = None
    associated_resource_type: str | None = None  # NIC, LB, NAT GW, etc.
    dns_fqdn: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class PrivateDnsVnetLink:
    id: str
    name: str
    vnet_id: str
    vnet_name: str
    registration_enabled: bool = False


@dataclass
class PrivateDnsZone:
    id: str
    name: str
    resource_group: str
    record_count: int = 0
    vnet_links: list[PrivateDnsVnetLink] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class LocalNetworkGateway:
    id: str
    name: str
    resource_group: str
    location: str
    gateway_ip: str | None = None
    address_prefixes: list[str] = field(default_factory=list)
    bgp_asn: int | None = None
    bgp_peering_address: str | None = None
    fqdn: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ExpressRoutePeering:
    name: str
    peering_type: str  # AzurePrivatePeering, MicrosoftPeering, AzurePublicPeering
    state: str  # Enabled, Disabled
    azure_asn: int | None = None
    peer_asn: int | None = None
    primary_prefix: str | None = None
    secondary_prefix: str | None = None
    vlan_id: int | None = None


@dataclass
class ExpressRouteCircuit:
    id: str
    name: str
    resource_group: str
    location: str
    service_provider: str | None = None
    peering_location: str | None = None
    bandwidth_mbps: int | None = None
    sku_tier: str | None = None  # Standard, Premium
    sku_family: str | None = None  # MeteredData, UnlimitedData
    circuit_provisioning_state: str | None = None
    service_provider_provisioning_state: str | None = None
    peerings: list[ExpressRoutePeering] = field(default_factory=list)
    gateway_connections: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class BgpPeerStatus:
    neighbor: str
    asn: int | None = None
    state: str = "Unknown"  # Connected, Connecting, Idle, etc.
    routes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    connected_duration: str | None = None
    gateway_name: str = ""


@dataclass
class HubVnetConnection:
    id: str
    name: str
    remote_vnet_id: str
    remote_vnet_name: str
    allow_hub_to_remote: bool = True
    allow_remote_to_hub: bool = True
    enable_internet_security: bool = False
    provisioning_state: str = ""


@dataclass
class HubRouteTable:
    id: str
    name: str
    routes: list[dict[str, str]] = field(default_factory=list)
    associated_connections: list[str] = field(default_factory=list)
    propagating_connections: list[str] = field(default_factory=list)
    provisioning_state: str = ""


@dataclass
class VirtualHub:
    id: str
    name: str
    resource_group: str
    location: str
    virtual_wan_id: str | None = None
    address_prefix: str | None = None
    sku: str | None = None
    provisioning_state: str = ""
    routing_state: str = ""
    vnet_connections: list[HubVnetConnection] = field(default_factory=list)
    route_tables: list[HubRouteTable] = field(default_factory=list)
    vpn_gateway_id: str | None = None
    er_gateway_id: str | None = None
    p2s_gateway_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class VirtualWan:
    id: str
    name: str
    resource_group: str
    location: str
    wan_type: str = "Standard"  # Basic or Standard
    disable_vpn_encryption: bool = False
    allow_branch_to_branch: bool = True
    allow_vnet_to_vnet: bool = True
    hub_ids: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class LoadBalancerFrontend:
    name: str
    private_ip: str | None = None
    public_ip_id: str | None = None
    subnet_id: str | None = None


@dataclass
class LoadBalancerBackendPool:
    name: str
    ip_count: int = 0


@dataclass
class LoadBalancerRule:
    name: str
    frontend_port: int = 0
    backend_port: int = 0
    protocol: str = ""
    frontend_name: str = ""
    backend_pool_name: str = ""
    probe_name: str = ""


@dataclass
class LoadBalancerProbe:
    name: str
    protocol: str = ""
    port: int = 0
    interval: int = 15
    path: str | None = None


@dataclass
class LoadBalancer:
    id: str
    name: str
    resource_group: str
    location: str
    sku: str = "Standard"
    is_internal: bool = False
    frontends: list[LoadBalancerFrontend] = field(default_factory=list)
    backend_pools: list[LoadBalancerBackendPool] = field(default_factory=list)
    rules: list[LoadBalancerRule] = field(default_factory=list)
    probes: list[LoadBalancerProbe] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class AppGatewayListener:
    name: str
    frontend_ip_name: str = ""
    port: int = 0
    protocol: str = ""
    host_name: str | None = None


@dataclass
class AppGatewayBackendPool:
    name: str
    target_count: int = 0


@dataclass
class AppGatewayRoutingRule:
    name: str
    rule_type: str = ""
    listener_name: str = ""
    backend_pool_name: str = ""
    priority: int | None = None


@dataclass
class ApplicationGateway:
    id: str
    name: str
    resource_group: str
    location: str
    sku_name: str | None = None
    sku_tier: str | None = None
    capacity: int | None = None
    waf_enabled: bool = False
    waf_mode: str | None = None  # Detection or Prevention
    subnet_id: str | None = None
    listeners: list[AppGatewayListener] = field(default_factory=list)
    backend_pools: list[AppGatewayBackendPool] = field(default_factory=list)
    routing_rules: list[AppGatewayRoutingRule] = field(default_factory=list)
    public_ip_ids: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class Topology:
    """Top-level container for discovered network topology."""

    subscription_ids: list[str] = field(default_factory=list)
    # Kept for backward compat with existing JSON files
    subscription_id: str = ""
    vnets: list[VNet] = field(default_factory=list)
    route_tables: list[RouteTable] = field(default_factory=list)
    nsgs: list[NSG] = field(default_factory=list)
    nat_gateways: list[NatGateway] = field(default_factory=list)
    vpn_gateways: list[VpnGateway] = field(default_factory=list)
    public_ips: list[PublicIP] = field(default_factory=list)
    private_dns_zones: list[PrivateDnsZone] = field(default_factory=list)
    local_network_gateways: list[LocalNetworkGateway] = field(default_factory=list)
    expressroute_circuits: list[ExpressRouteCircuit] = field(default_factory=list)
    bgp_peers: list[BgpPeerStatus] = field(default_factory=list)
    virtual_wans: list[VirtualWan] = field(default_factory=list)
    virtual_hubs: list[VirtualHub] = field(default_factory=list)
    load_balancers: list[LoadBalancer] = field(default_factory=list)
    application_gateways: list[ApplicationGateway] = field(default_factory=list)
