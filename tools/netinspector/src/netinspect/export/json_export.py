"""JSON export for topology data."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from netinspect.models.types import Topology


def export_json(topology: Topology, output_path: Path) -> None:
    """Export the full topology as a JSON snapshot."""
    data = asdict(topology)
    output_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def load_json(input_path: Path) -> dict:
    """Load a topology JSON snapshot."""
    return json.loads(input_path.read_text(encoding="utf-8"))
