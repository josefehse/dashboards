"""NSG effective rules evaluation for Azure network topology.

Evaluates whether a given traffic flow (source IP, dest IP, port, protocol)
would be allowed or denied by the NSG rules on a subnet.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from netinspect.models.types import (
    NSG,
    SecurityRule,
    SecurityRuleAccess,
    SecurityRuleDirection,
    Topology,
)


@dataclass
class SecurityVerdict:
    """Result of evaluating NSG rules for a traffic flow."""

    allowed: bool
    matching_rule: str  # Name of the rule that matched
    nsg_name: str
    direction: str
    reason: str  # Human-readable explanation


# Well-known Azure service tags mapped to CIDR ranges (simplified)
SERVICE_TAG_PREFIXES = {
    "virtualnetwork": None,  # Resolved dynamically
    "internet": None,
    "azureloadbalancer": ["168.63.129.16/32"],
    "azurecloud": None,  # Too large to enumerate
    "*": None,
}


def evaluate_nsg(
    topology: Topology,
    subnet_id: str,
    direction: str,
    source_ip: str,
    dest_ip: str,
    dest_port: int,
    protocol: str = "TCP",
) -> SecurityVerdict | None:
    """Evaluate NSG rules for a traffic flow on a specific subnet.

    Returns None if no NSG is associated with the subnet.
    """
    # Find the subnet and its NSG
    nsg = _find_subnet_nsg(topology, subnet_id)
    if nsg is None:
        return None

    rule_dir = SecurityRuleDirection(direction)

    # Get all VNet address spaces for service tag resolution
    vnet_prefixes = []
    for v in topology.vnets:
        vnet_prefixes.extend(v.address_spaces)

    # Filter rules by direction and sort by priority
    matching_rules = [
        r for r in nsg.rules if r.direction == rule_dir
    ]
    matching_rules.sort(key=lambda r: r.priority)

    # Evaluate rules in priority order (lowest number = highest priority)
    for rule in matching_rules:
        if _rule_matches(
            rule, source_ip, dest_ip, dest_port, protocol, vnet_prefixes,
        ):
            allowed = rule.access == SecurityRuleAccess.ALLOW
            return SecurityVerdict(
                allowed=allowed,
                matching_rule=rule.name,
                nsg_name=nsg.name,
                direction=direction,
                reason=(
                    f"{'✅ Allowed' if allowed else '🚫 Denied'} by rule "
                    f"'{rule.name}' (priority {rule.priority})"
                ),
            )

    # Should not reach here — default deny rules always exist
    return SecurityVerdict(
        allowed=False,
        matching_rule="ImplicitDeny",
        nsg_name=nsg.name,
        direction=direction,
        reason="🚫 Denied by implicit deny (no matching rule found)",
    )


def _find_subnet_nsg(topology: Topology, subnet_id: str) -> NSG | None:
    """Find the NSG associated with a subnet."""
    nsg_id = None
    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            if subnet.id == subnet_id and subnet.nsg_id:
                nsg_id = subnet.nsg_id
                break

    if not nsg_id:
        return None

    for nsg in topology.nsgs:
        if nsg.id == nsg_id:
            return nsg

    return None


def _rule_matches(
    rule: SecurityRule,
    source_ip: str,
    dest_ip: str,
    dest_port: int,
    protocol: str,
    vnet_prefixes: list[str],
) -> bool:
    """Check if a security rule matches the given traffic flow."""
    # Check protocol
    if rule.protocol != "*" and rule.protocol.upper() != protocol.upper():
        return False

    # Check source address
    if not _address_matches(
        rule.source_address_prefix,
        rule.source_address_prefixes,
        source_ip,
        vnet_prefixes,
    ):
        return False

    # Check destination address
    if not _address_matches(
        rule.destination_address_prefix,
        rule.destination_address_prefixes,
        dest_ip,
        vnet_prefixes,
    ):
        return False

    # Check destination port
    if not _port_matches(rule.destination_port_range, dest_port):
        return False

    return True


def _address_matches(
    prefix: str | None,
    prefixes: list[str],
    ip: str,
    vnet_prefixes: list[str],
) -> bool:
    """Check if an IP matches an NSG address specification."""
    all_prefixes = []
    if prefix:
        all_prefixes.append(prefix)
    all_prefixes.extend(prefixes)

    if not all_prefixes:
        return True  # No restriction

    for p in all_prefixes:
        p_lower = p.lower().strip()

        if p_lower == "*" or p_lower == "any":
            return True

        if p_lower == "virtualnetwork":
            for vp in vnet_prefixes:
                if _ip_in_prefix(ip, vp):
                    return True
            continue

        if p_lower == "internet":
            if not any(_ip_in_prefix(ip, vp) for vp in vnet_prefixes):
                return True
            continue

        if p_lower == "azureloadbalancer":
            if _ip_in_prefix(ip, "168.63.129.16/32"):
                return True
            continue

        # Direct CIDR or IP match
        if _ip_in_prefix(ip, p):
            return True

    return False


def _ip_in_prefix(ip: str, prefix: str) -> bool:
    """Check if an IP address falls within a CIDR prefix."""
    try:
        addr = ipaddress.ip_address(ip)
        network = ipaddress.ip_network(prefix, strict=False)
        return addr in network
    except ValueError:
        return False


def _port_matches(port_range: str | None, port: int) -> bool:
    """Check if a port matches an NSG port range specification."""
    if not port_range or port_range == "*":
        return True

    # Handle comma-separated or range
    for part in port_range.split(","):
        part = part.strip()
        if "-" in part:
            try:
                low, high = part.split("-", 1)
                if int(low) <= port <= int(high):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == port:
                    return True
            except ValueError:
                continue

    return False
