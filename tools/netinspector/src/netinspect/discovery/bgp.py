"""Discover BGP peer status and learned routes from gateways."""

from __future__ import annotations

from azure.mgmt.network import NetworkManagementClient
from rich.console import Console

from netinspect.models.types import BgpPeerStatus, VpnGateway

console = Console()


def discover_bgp_peers(
    network_client: NetworkManagementClient,
    vpn_gateways: list[VpnGateway],
) -> list[BgpPeerStatus]:
    """Get BGP peer status from all BGP-enabled gateways."""
    peers: list[BgpPeerStatus] = []

    for gw in vpn_gateways:
        if not gw.bgp_enabled:
            continue

        try:
            # get_bgp_peer_status is a long-running operation
            poller = (
                network_client.virtual_network_gateways
                .begin_get_bgp_peer_status(gw.resource_group, gw.name)
            )
            result = poller.result()

            for raw in result.value or []:
                peer = BgpPeerStatus(
                    neighbor=raw.neighbor or "",
                    asn=raw.asn,
                    state=raw.state or "Unknown",
                    routes_received=raw.routes_received or 0,
                    messages_sent=raw.messages_sent or 0,
                    messages_received=raw.messages_received or 0,
                    connected_duration=raw.connected_duration,
                    gateway_name=gw.name,
                )
                peers.append(peer)

                state_icon = "🟢" if peer.state == "Connected" else "🔴"
                console.print(
                    f"  BGP peer on [cyan]{gw.name}[/cyan]: "
                    f"{state_icon} {peer.neighbor} "
                    f"(ASN {peer.asn}, {peer.state}, "
                    f"{peer.routes_received} routes)"
                )

        except Exception as e:
            console.print(
                f"  [yellow]Could not get BGP status for "
                f"{gw.name}: {e}[/yellow]"
            )

    if not peers:
        console.print("  [dim]No BGP peers found (BGP not enabled on any gateway).[/dim]")

    return peers
