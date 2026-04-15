"""NetworkX-based topology graph model."""

from __future__ import annotations

import networkx as nx

from netinspect.models.types import Topology


class TopologyGraph:
    """Directed graph representation of Azure network topology.

    Node types: vnet, subnet, nsg, route_table, nat_gateway, vpn_gateway,
                public_ip, private_dns_zone, local_gateway,
                expressroute_circuit, bgp_peer, virtual_wan, virtual_hub
    Edge types: contains, peers_with, secured_by, routed_by, nat_by,
                gateway_of, assigned_to, dns_linked, vpn_connection,
                er_connection, bgp_peer_of, hub_in_wan, hub_vnet_connection
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    def build_from_topology(self, topology: Topology) -> None:
        """Populate the graph from a discovered Topology."""
        self._add_vnets(topology)
        self._add_route_tables(topology)
        self._add_nsgs(topology)
        self._add_nat_gateways(topology)
        self._add_vpn_gateways(topology)
        self._add_public_ips(topology)
        self._add_private_dns_zones(topology)
        self._add_local_gateways(topology)
        self._add_expressroute_circuits(topology)
        self._add_bgp_peers(topology)
        self._add_virtual_wans(topology)
        self._add_virtual_hubs(topology)
        self._add_load_balancers(topology)
        self._add_application_gateways(topology)
        self._link_subnets_to_resources(topology)
        self._link_vpn_connections(topology)

    def _add_vnets(self, topology: Topology) -> None:
        for vnet in topology.vnets:
            self.graph.add_node(
                vnet.id,
                type="vnet",
                name=vnet.name,
                resource_group=vnet.resource_group,
                location=vnet.location,
                address_spaces=vnet.address_spaces,
            )
            for subnet in vnet.subnets:
                self.graph.add_node(
                    subnet.id,
                    type="subnet",
                    name=subnet.name,
                    address_prefix=subnet.address_prefix,
                    vnet=vnet.name,
                )
                self.graph.add_edge(vnet.id, subnet.id, type="contains")

            for peering in vnet.peerings:
                # Ensure remote VNet node exists (may be in a different subscription)
                if not self.graph.has_node(peering.remote_vnet_id):
                    self.graph.add_node(
                        peering.remote_vnet_id,
                        type="vnet",
                        name=peering.remote_vnet_name,
                        external=True,
                    )
                self.graph.add_edge(
                    vnet.id,
                    peering.remote_vnet_id,
                    type="peers_with",
                    state=peering.state.value,
                    allow_forwarded_traffic=peering.allow_forwarded_traffic,
                    allow_gateway_transit=peering.allow_gateway_transit,
                    use_remote_gateways=peering.use_remote_gateways,
                )

    def _add_route_tables(self, topology: Topology) -> None:
        for rt in topology.route_tables:
            self.graph.add_node(
                rt.id,
                type="route_table",
                name=rt.name,
                resource_group=rt.resource_group,
                route_count=len(rt.routes),
                disable_bgp_propagation=rt.disable_bgp_route_propagation,
            )

    def _add_nsgs(self, topology: Topology) -> None:
        for nsg in topology.nsgs:
            self.graph.add_node(
                nsg.id,
                type="nsg",
                name=nsg.name,
                resource_group=nsg.resource_group,
                rule_count=len(nsg.rules),
            )

    def _link_subnets_to_resources(self, topology: Topology) -> None:
        """Create edges between subnets and their associated NSGs/route tables/NAT GWs."""
        for vnet in topology.vnets:
            for subnet in vnet.subnets:
                if subnet.nsg_id and self.graph.has_node(subnet.nsg_id):
                    self.graph.add_edge(subnet.id, subnet.nsg_id, type="secured_by")
                if subnet.route_table_id and self.graph.has_node(subnet.route_table_id):
                    self.graph.add_edge(subnet.id, subnet.route_table_id, type="routed_by")
                if subnet.nat_gateway_id and self.graph.has_node(subnet.nat_gateway_id):
                    self.graph.add_edge(subnet.id, subnet.nat_gateway_id, type="nat_by")

    def _add_nat_gateways(self, topology: Topology) -> None:
        for ng in topology.nat_gateways:
            self.graph.add_node(
                ng.id,
                type="nat_gateway",
                name=ng.name,
                resource_group=ng.resource_group,
                idle_timeout=ng.idle_timeout_minutes,
                public_ip_count=len(ng.public_ip_addresses),
            )

    def _add_vpn_gateways(self, topology: Topology) -> None:
        for gw in topology.vpn_gateways:
            self.graph.add_node(
                gw.id,
                type="vpn_gateway",
                name=gw.name,
                resource_group=gw.resource_group,
                gateway_type=gw.gateway_type,
                sku=gw.sku,
                bgp_enabled=gw.bgp_enabled,
                bgp_asn=gw.bgp_asn,
                active_active=gw.active_active,
            )
            # Link gateway to its VNet
            if gw.vnet_id and self.graph.has_node(gw.vnet_id):
                self.graph.add_edge(gw.vnet_id, gw.id, type="gateway_of")

    def _add_public_ips(self, topology: Topology) -> None:
        for pip in topology.public_ips:
            self.graph.add_node(
                pip.id,
                type="public_ip",
                name=pip.name,
                ip_address=pip.ip_address,
                sku=pip.sku,
                associated_type=pip.associated_resource_type,
            )
            if pip.associated_resource_id:
                # Try to link to the parent resource in the graph
                target = pip.associated_resource_id
                # For NICs, link up to the subnet's VNet instead
                if self.graph.has_node(target):
                    self.graph.add_edge(
                        target, pip.id, type="assigned_to"
                    )

    def _add_private_dns_zones(self, topology: Topology) -> None:
        for zone in topology.private_dns_zones:
            self.graph.add_node(
                zone.id,
                type="private_dns_zone",
                name=zone.name,
                record_count=zone.record_count,
                link_count=len(zone.vnet_links),
            )
            for link in zone.vnet_links:
                if self.graph.has_node(link.vnet_id):
                    self.graph.add_edge(
                        link.vnet_id, zone.id,
                        type="dns_linked",
                        registration=link.registration_enabled,
                    )

    def _add_local_gateways(self, topology: Topology) -> None:
        for lgw in topology.local_network_gateways:
            self.graph.add_node(
                lgw.id,
                type="local_gateway",
                name=lgw.name,
                resource_group=lgw.resource_group,
                gateway_ip=lgw.gateway_ip,
                address_prefixes=lgw.address_prefixes,
                bgp_asn=lgw.bgp_asn,
            )

    def _add_expressroute_circuits(self, topology: Topology) -> None:
        for er in topology.expressroute_circuits:
            self.graph.add_node(
                er.id,
                type="expressroute_circuit",
                name=er.name,
                resource_group=er.resource_group,
                service_provider=er.service_provider,
                bandwidth_mbps=er.bandwidth_mbps,
                peering_count=len(er.peerings),
            )

    def _add_bgp_peers(self, topology: Topology) -> None:
        for peer in topology.bgp_peers:
            node_id = f"bgp_{peer.gateway_name}_{peer.neighbor}"
            self.graph.add_node(
                node_id,
                type="bgp_peer",
                neighbor=peer.neighbor,
                asn=peer.asn,
                state=peer.state,
                routes_received=peer.routes_received,
                gateway_name=peer.gateway_name,
            )
            # Link to the parent gateway
            for gw in topology.vpn_gateways:
                if gw.name == peer.gateway_name:
                    self.graph.add_edge(
                        gw.id, node_id, type="bgp_peer_of"
                    )
                    break

    def _add_virtual_wans(self, topology: Topology) -> None:
        for wan in topology.virtual_wans:
            self.graph.add_node(
                wan.id,
                type="virtual_wan",
                name=wan.name,
                resource_group=wan.resource_group,
                wan_type=wan.wan_type,
                allow_branch_to_branch=wan.allow_branch_to_branch,
            )

    def _add_virtual_hubs(self, topology: Topology) -> None:
        for hub in topology.virtual_hubs:
            self.graph.add_node(
                hub.id,
                type="virtual_hub",
                name=hub.name,
                resource_group=hub.resource_group,
                address_prefix=hub.address_prefix,
                routing_state=hub.routing_state,
            )
            # Link hub to its vWAN
            if hub.virtual_wan_id and self.graph.has_node(hub.virtual_wan_id):
                self.graph.add_edge(
                    hub.virtual_wan_id, hub.id, type="hub_in_wan",
                )
            # Link hub to connected VNets
            for conn in hub.vnet_connections:
                if conn.remote_vnet_id and self.graph.has_node(
                    conn.remote_vnet_id
                ):
                    self.graph.add_edge(
                        hub.id, conn.remote_vnet_id,
                        type="hub_vnet_connection",
                        connection_name=conn.name,
                        internet_security=conn.enable_internet_security,
                    )
            # Link hub to its gateways
            for gw_id in [hub.vpn_gateway_id, hub.er_gateway_id,
                          hub.p2s_gateway_id]:
                if gw_id and self.graph.has_node(gw_id):
                    self.graph.add_edge(
                        hub.id, gw_id, type="gateway_of",
                    )

    def _add_load_balancers(self, topology: Topology) -> None:
        for lb in topology.load_balancers:
            self.graph.add_node(
                lb.id,
                type="load_balancer",
                name=lb.name,
                resource_group=lb.resource_group,
                sku=lb.sku,
                is_internal=lb.is_internal,
                rule_count=len(lb.rules),
            )
            # Link internal LBs to their subnet
            for fe in lb.frontends:
                if fe.subnet_id and self.graph.has_node(fe.subnet_id):
                    self.graph.add_edge(
                        fe.subnet_id, lb.id, type="contains",
                    )

    def _add_application_gateways(self, topology: Topology) -> None:
        for agw in topology.application_gateways:
            self.graph.add_node(
                agw.id,
                type="application_gateway",
                name=agw.name,
                resource_group=agw.resource_group,
                sku=agw.sku_tier,
                waf_enabled=agw.waf_enabled,
            )
            # Link to subnet
            if agw.subnet_id and self.graph.has_node(agw.subnet_id):
                self.graph.add_edge(
                    agw.subnet_id, agw.id, type="contains",
                )

    def _link_vpn_connections(self, topology: Topology) -> None:
        """Create edges between VPN gateways and their connection targets."""
        for gw in topology.vpn_gateways:
            for conn in gw.connections:
                if conn.remote_gateway_id:
                    target = conn.remote_gateway_id
                    if not self.graph.has_node(target):
                        # Create stub node for unknown remotes
                        name = target.split("/")[-1]
                        self.graph.add_node(
                            target, type="local_gateway",
                            name=name, external=True,
                        )
                    self.graph.add_edge(
                        gw.id, target,
                        type="vpn_connection",
                        connection_name=conn.name,
                        connection_type=conn.connection_type,
                        status=conn.status,
                        enable_bgp=conn.enable_bgp,
                    )
        # Link ER circuits to ER gateways
        for gw in topology.vpn_gateways:
            if gw.gateway_type == "ExpressRoute":
                for conn in gw.connections:
                    for er in topology.expressroute_circuits:
                        if er.id and conn.remote_gateway_id and (
                            er.id.lower() in conn.remote_gateway_id.lower()
                        ):
                            self.graph.add_edge(
                                gw.id, er.id, type="er_connection",
                                connection_name=conn.name,
                            )

    def get_vnets(self) -> list[dict]:
        """Return all VNet nodes."""
        return [
            {"id": n, **self.graph.nodes[n]}
            for n in self.graph.nodes
            if self.graph.nodes[n].get("type") == "vnet"
        ]

    def get_peers(self, vnet_id: str) -> list[str]:
        """Return IDs of VNets peered with the given VNet."""
        return [
            target
            for _, target, data in self.graph.edges(vnet_id, data=True)
            if data.get("type") == "peers_with"
        ]

    def to_json(self) -> dict:
        """Serialize the graph to a JSON-compatible dict."""
        return nx.node_link_data(self.graph)

    @classmethod
    def from_json(cls, data: dict) -> TopologyGraph:
        """Deserialize a graph from JSON data."""
        tg = cls()
        tg.graph = nx.node_link_graph(data)
        return tg

    def summary(self) -> dict:
        """Return a summary of the topology."""
        nodes = self.graph.nodes(data=True)
        type_counts: dict[str, int] = {}
        for _, data in nodes:
            t = data.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        edge_type_counts: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            t = data.get("type", "unknown")
            edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
        }


def build_topology_graph(topology: Topology) -> TopologyGraph:
    """Convenience function to build a TopologyGraph from a Topology."""
    tg = TopologyGraph()
    tg.build_from_topology(topology)
    return tg
