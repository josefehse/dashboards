from __future__ import annotations

import json
from dataclasses import asdict

from typer.testing import CliRunner

from netinspect.cli import app
from netinspect.export.dns import generate_dns_report
from netinspect.export.reporting import export_dns_report, export_topology_report
from netinspect.models.types import PrivateDnsVnetLink, PrivateDnsZone, Topology, VNet


def _sample_topology() -> Topology:
    return Topology(
        subscription_ids=["sub-123"],
        subscription_id="sub-123",
        vnets=[
            VNet(
                id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/hub-vnet",
                name="hub-vnet",
                resource_group="rg",
                location="westeurope",
                address_spaces=["10.0.0.0/16"],
                dns_servers=["10.1.0.4", "8.8.8.8"],
            ),
            VNet(
                id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/spoke-vnet",
                name="spoke-vnet",
                resource_group="rg",
                location="westeurope",
                address_spaces=["10.2.0.0/16"],
            ),
        ],
        private_dns_zones=[
            PrivateDnsZone(
                id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/privateDnsZones/privatelink.database.windows.net",
                name="privatelink.database.windows.net",
                resource_group="rg",
                record_count=3,
                vnet_links=[
                    PrivateDnsVnetLink(
                        id="link-1",
                        name="hub-link",
                        vnet_id="hub-vnet-id",
                        vnet_name="hub-vnet",
                        registration_enabled=True,
                    )
                ],
            )
        ],
    )


def test_export_topology_report_writes_html(tmp_path):
    output = tmp_path / "report.html"

    export_topology_report(_sample_topology(), output)

    html = output.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "Network Topology Report" in html
    assert "Static HTML export for netinspect topology summaries" in html
    assert "Network Topology Diagrams" in html


def test_generate_dns_report_identifies_private_resolvers():
    report = generate_dns_report(_sample_topology())

    assert "# DNS Configuration Report" in report
    assert "Unique private resolver IPs:** 1" in report
    assert "| `10.1.0.4` | hub-vnet |" in report
    assert "| hub-vnet | Custom | `10.1.0.4`, `8.8.8.8` | 10.1.0.4 | 8.8.8.8 |" in report
    assert "### privatelink.database.windows.net" in report


def test_cli_dns_report_supports_html_output(tmp_path):
    input_path = tmp_path / "topology.json"
    output_path = tmp_path / "dns-report.html"
    input_path.write_text(json.dumps(asdict(_sample_topology())), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, [
        "dns-report",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ])

    assert result.exit_code == 0, result.stdout
    html = output_path.read_text(encoding="utf-8")
    assert "DNS Configuration Report" in html
    assert "Static HTML export highlighting VNet DNS settings" in html


def test_export_dns_report_writes_markdown_by_default(tmp_path):
    output = tmp_path / "dns-report.md"

    export_dns_report(_sample_topology(), output)

    markdown = output.read_text(encoding="utf-8")
    assert markdown.startswith("# DNS Configuration Report")
