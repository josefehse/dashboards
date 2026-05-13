"""Report export dispatchers."""

from __future__ import annotations

from pathlib import Path

from netinspect.export.dns import generate_dns_report
from netinspect.export.html import generate_dns_html, generate_topology_html
from netinspect.export.markdown import export_report as export_markdown_report
from netinspect.models.types import Topology


def export_topology_report(
    topology: Topology, output_path: Path, *, include_analysis: bool = False,
) -> None:
    """Export a topology report in Markdown or HTML based on file suffix."""
    if _is_html_output(output_path):
        html = generate_topology_html(topology, include_analysis=include_analysis)
        output_path.write_text(html, encoding="utf-8")
        return

    export_markdown_report(topology, output_path, include_analysis=include_analysis)


def export_dns_report(topology: Topology, output_path: Path) -> None:
    """Export a DNS report in Markdown or HTML based on file suffix."""
    markdown = generate_dns_report(topology)
    if _is_html_output(output_path):
        html = generate_dns_html(topology)
        output_path.write_text(html, encoding="utf-8")
        return

    output_path.write_text(markdown, encoding="utf-8")


def _is_html_output(output_path: Path) -> bool:
    return output_path.suffix.lower() in {".html", ".htm"}
