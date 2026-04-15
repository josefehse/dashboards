"""Parse Azure VNet flow log JSON into flat records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROTOCOL_MAP = {"6": "TCP", "17": "UDP"}
DIRECTION_MAP = {"I": "Inbound", "O": "Outbound"}
STATE_MAP = {"B": "Begin", "C": "Continuing", "E": "End"}

TUPLE_FIELDS = [
    "timestamp_epoch_ms",
    "src_ip",
    "dst_ip",
    "src_port",
    "dst_port",
    "protocol",
    "direction",
    "state",
    "encryption",
    "packets_src_to_dst",
    "bytes_src_to_dst",
    "packets_dst_to_src",
    "bytes_dst_to_src",
]


def parse_flow_tuple(tuple_str: str) -> dict[str, Any]:
    """Parse a single CSV flow tuple string into a dict."""
    parts = tuple_str.split(",")
    if len(parts) != 13:
        raise ValueError(f"Expected 13 fields in flow tuple, got {len(parts)}: {tuple_str}")

    epoch_ms = int(parts[0])
    flow_time = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)

    return {
        "timestamp_epoch_ms": epoch_ms,
        "flow_time": flow_time,
        "src_ip": parts[1],
        "dst_ip": parts[2],
        "src_port": int(parts[3]),
        "dst_port": int(parts[4]),
        "protocol": PROTOCOL_MAP.get(parts[5], parts[5]),
        "direction": DIRECTION_MAP.get(parts[6], parts[6]),
        "state": STATE_MAP.get(parts[7], parts[7]),
        "encryption": parts[8],
        "packets_src_to_dst": int(parts[9]),
        "bytes_src_to_dst": int(parts[10]),
        "packets_dst_to_src": int(parts[11]),
        "bytes_dst_to_src": int(parts[12]),
    }


def parse_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a single flow log record into a list of flat flow dicts."""
    record_time = record.get("time", "")
    common = {
        "record_time": record_time,
        "flow_log_guid": record.get("flowLogGUID", ""),
        "mac_address": record.get("macAddress", ""),
        "flow_log_resource": record.get("flowLogResourceID", ""),
        "target_resource": record.get("targetResourceID", ""),
    }

    rows: list[dict[str, Any]] = []
    flow_records = record.get("flowRecords", {})
    for flow in flow_records.get("flows", []):
        acl_id = flow.get("aclID", "")
        for group in flow.get("flowGroups", []):
            rule_name = group.get("rule", "")
            for tuple_str in group.get("flowTuples", []):
                parsed = parse_flow_tuple(tuple_str)
                row = {**common, "acl_id": acl_id, "rule_name": rule_name, **parsed}
                rows.append(row)
    return rows


def parse_flowlog_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse an entire flow log JSON document into flat records."""
    rows: list[dict[str, Any]] = []
    for record in data.get("records", []):
        rows.extend(parse_record(record))
    return rows


def parse_flowlog_file(path: str | Path) -> list[dict[str, Any]]:
    """Parse a flow log JSON file from disk."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_flowlog_json(data)
