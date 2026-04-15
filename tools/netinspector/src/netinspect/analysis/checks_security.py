"""Security analysis checks aligned with WAF Security pillar."""

from __future__ import annotations

from netinspect.analysis.findings import (
    AnalysisReport,
    Category,
    Finding,
    Severity,
)
from netinspect.models.types import Topology

CAT = Category.SECURITY


def check_security(topology: Topology, report: AnalysisReport) -> None:
    """Run all security checks against the topology."""
    _check_subnets_without_nsg(topology, report)
    _check_permissive_nsg_rules(topology, report)
    _check_unused_nsgs(topology, report)
    _check_unprotected_public_ips(topology, report)
    _check_ssh_rdp_open(topology, report)
    _check_nsg_deny_all_missing(topology, report)


def _check_subnets_without_nsg(
    topology: Topology, report: AnalysisReport,
) -> None:
    """SE:06 — Every subnet should have an NSG."""
    skip = {"gatewaysubnet", "azurefirewallsubnet",
            "azurefirewallmanagementsubnet", "routeserversubnet"}
    for vnet in topology.vnets:
        for subnet in vnet.subnets:
            if subnet.name.lower() in skip:
                continue
            if not subnet.nsg_id:
                report.add(Finding(
                    severity=Severity.CRITICAL,
                    category=CAT,
                    title="Subnet without NSG",
                    description=(
                        f"Subnet '{subnet.name}' in VNet '{vnet.name}' "
                        f"has no Network Security Group attached. All "
                        f"traffic is implicitly allowed."
                    ),
                    recommendation=(
                        "Attach an NSG to this subnet to enforce "
                        "network-level access control."
                    ),
                    resource_id=subnet.id,
                    resource_name=f"{vnet.name}/{subnet.name}",
                    waf_pillar="SE:06",
                ))


def _check_permissive_nsg_rules(
    topology: Topology, report: AnalysisReport,
) -> None:
    """SE:06 — Flag overly permissive inbound rules."""
    for nsg in topology.nsgs:
        for rule in nsg.rules:
            if rule.direction.value != "Inbound":
                continue
            if rule.access.value != "Allow":
                continue

            src = rule.source_address_prefix or ""
            dst_port = rule.destination_port_range or ""
            proto = rule.protocol or ""

            # Allow all from any source
            if src in ("*", "0.0.0.0/0", "Internet") and dst_port == "*" and proto == "*":
                report.add(Finding(
                    severity=Severity.CRITICAL,
                    category=CAT,
                    title="Allow-all inbound rule from Internet",
                    description=(
                        f"NSG '{nsg.name}' rule '{rule.name}' "
                        f"(priority {rule.priority}) allows ALL inbound "
                        f"traffic from {src}. This exposes all services."
                    ),
                    recommendation=(
                        "Restrict to specific ports and source addresses. "
                        "Use Application Security Groups where possible."
                    ),
                    resource_id=nsg.id,
                    resource_name=nsg.name,
                    waf_pillar="SE:06",
                ))


def _check_ssh_rdp_open(
    topology: Topology, report: AnalysisReport,
) -> None:
    """SE:06 — SSH/RDP open to the internet."""
    mgmt_ports = {"22", "3389"}
    for nsg in topology.nsgs:
        for rule in nsg.rules:
            if rule.direction.value != "Inbound":
                continue
            if rule.access.value != "Allow":
                continue

            src = rule.source_address_prefix or ""
            if src not in ("*", "0.0.0.0/0", "Internet"):
                continue

            dst_port = rule.destination_port_range or ""
            if dst_port in mgmt_ports:
                report.add(Finding(
                    severity=Severity.CRITICAL,
                    category=CAT,
                    title=f"Management port {dst_port} open to Internet",
                    description=(
                        f"NSG '{nsg.name}' rule '{rule.name}' allows "
                        f"port {dst_port} from Internet. This is a "
                        f"common attack vector."
                    ),
                    recommendation=(
                        "Use Azure Bastion or Just-in-Time access "
                        "instead of exposing management ports directly."
                    ),
                    resource_id=nsg.id,
                    resource_name=nsg.name,
                    waf_pillar="SE:06",
                ))


def _check_unused_nsgs(
    topology: Topology, report: AnalysisReport,
) -> None:
    """Operational — NSGs not attached to any subnet or NIC."""
    for nsg in topology.nsgs:
        if not nsg.associated_subnets and not nsg.associated_nics:
            report.add(Finding(
                severity=Severity.INFO,
                category=CAT,
                title="Unattached NSG",
                description=(
                    f"NSG '{nsg.name}' is not associated with any "
                    f"subnet or NIC."
                ),
                recommendation=(
                    "Review if this NSG is still needed. Remove "
                    "orphaned NSGs to reduce management overhead."
                ),
                resource_id=nsg.id,
                resource_name=nsg.name,
            ))


def _check_unprotected_public_ips(
    topology: Topology, report: AnalysisReport,
) -> None:
    """SE:06 — Public IPs increase attack surface."""
    for pip in topology.public_ips:
        if not pip.associated_resource_id:
            continue
        # Check if the PIP's resource is behind an NSG
        assoc_type = (pip.associated_resource_type or "").lower()
        if assoc_type in ("nat gateway", "load balancer"):
            continue  # These are typically fine
        if "bastion" in (pip.associated_resource_id or "").lower():
            continue

        report.add(Finding(
            severity=Severity.INFO,
            category=CAT,
            title="Public IP attached to resource",
            description=(
                f"Public IP '{pip.name}' ({pip.ip_address}) is "
                f"attached to {pip.associated_resource_type}: "
                f"{pip.associated_resource_id.split('/')[-1]}. "
                f"Ensure this exposure is intentional."
            ),
            recommendation=(
                "Minimize public IP exposure. Consider Private "
                "Link or service endpoints where possible."
            ),
            resource_id=pip.id,
            resource_name=pip.name,
            waf_pillar="SE:06",
        ))


def _check_nsg_deny_all_missing(
    topology: Topology, report: AnalysisReport,
) -> None:
    """SE:06 — Custom deny-all as last rule is a best practice."""
    for nsg in topology.nsgs:
        if not nsg.associated_subnets and not nsg.associated_nics:
            continue
        custom_rules = [
            r for r in nsg.rules
            if not r.name.startswith("AllowVnet")
            and not r.name.startswith("AllowAzureLoadBalancer")
            and not r.name.startswith("DenyAll")
            and not r.name.startswith("AllowInternet")
        ]
        if not custom_rules:
            report.add(Finding(
                severity=Severity.WARNING,
                category=CAT,
                title="NSG with no custom rules",
                description=(
                    f"NSG '{nsg.name}' has only default rules. "
                    f"Default rules allow all VNet and LB traffic."
                ),
                recommendation=(
                    "Add explicit allow rules for expected traffic "
                    "and consider adding a low-priority deny-all rule."
                ),
                resource_id=nsg.id,
                resource_name=nsg.name,
                waf_pillar="SE:06",
            ))
