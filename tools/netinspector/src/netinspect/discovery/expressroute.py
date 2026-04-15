"""Discover ExpressRoute circuits and their peerings."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import ExpressRouteCircuit, ExpressRoutePeering

console = Console()


def discover_expressroute_circuits(
    network_client: NetworkManagementClient,
) -> list[ExpressRouteCircuit]:
    """Discover all ExpressRoute circuits in the subscription."""
    circuits = []
    try:
        for raw in network_client.express_route_circuits.list_all():
            circuit = _parse_circuit(raw)
            circuits.append(circuit)

            provider = circuit.service_provider or "unknown"
            bw = f"{circuit.bandwidth_mbps}Mbps" if circuit.bandwidth_mbps else "?"
            state = circuit.service_provider_provisioning_state or "?"
            console.print(
                f"  Discovered ER Circuit: [cyan]{circuit.name}[/cyan] "
                f"({provider}, {bw}, {state}, "
                f"{len(circuit.peerings)} peerings)"
            )
    except Exception as e:
        console.print(
            f"  [yellow]Could not list ExpressRoute circuits: {e}[/yellow]"
        )

    if not circuits:
        console.print("  [dim]No ExpressRoute circuits found.[/dim]")

    return circuits


def _parse_circuit(raw) -> ExpressRouteCircuit:
    """Parse an ExpressRoute circuit SDK object."""
    rg = _extract_resource_group(raw.id)

    # Parse peerings
    peerings = []
    for p in raw.peerings or []:
        peerings.append(ExpressRoutePeering(
            name=p.name or "",
            peering_type=p.peering_type or "",
            state=p.state or "Unknown",
            azure_asn=p.azure_asn,
            peer_asn=p.peer_asn,
            primary_prefix=p.primary_peer_address_prefix,
            secondary_prefix=p.secondary_peer_address_prefix,
            vlan_id=p.vlan_id,
        ))

    # Extract gateway connections from authorizations or connections
    gw_connections = []
    if raw.authorizations:
        for auth in raw.authorizations:
            if auth.id:
                gw_connections.append(auth.id)

    # Service provider info
    provider_name = None
    peering_location = None
    if raw.service_provider_properties:
        provider_name = raw.service_provider_properties.service_provider_name
        peering_location = raw.service_provider_properties.peering_location

    return ExpressRouteCircuit(
        id=raw.id,
        name=raw.name,
        resource_group=rg,
        location=raw.location,
        service_provider=provider_name,
        peering_location=peering_location,
        bandwidth_mbps=(
            raw.service_provider_properties.bandwidth_in_mbps
            if raw.service_provider_properties else None
        ),
        sku_tier=raw.sku.tier if raw.sku else None,
        sku_family=raw.sku.family if raw.sku else None,
        circuit_provisioning_state=raw.circuit_provisioning_state,
        service_provider_provisioning_state=(
            raw.service_provider_provisioning_state
        ),
        peerings=peerings,
        gateway_connections=gw_connections,
        tags=dict(raw.tags) if raw.tags else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""
