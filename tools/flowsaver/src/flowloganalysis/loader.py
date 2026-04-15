"""Load parsed flow log records into DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS flow_logs (
    record_time         TIMESTAMP WITH TIME ZONE,
    flow_log_guid       VARCHAR,
    mac_address         VARCHAR,
    flow_log_resource   VARCHAR,
    target_resource     VARCHAR,
    acl_id              VARCHAR,
    rule_name           VARCHAR,
    timestamp_epoch_ms  BIGINT,
    flow_time           TIMESTAMP WITH TIME ZONE,
    src_ip              VARCHAR,
    dst_ip              VARCHAR,
    src_port            INTEGER,
    dst_port            INTEGER,
    protocol            VARCHAR,
    direction           VARCHAR,
    state               VARCHAR,
    encryption          VARCHAR,
    packets_src_to_dst  BIGINT,
    bytes_src_to_dst    BIGINT,
    packets_dst_to_src  BIGINT,
    bytes_dst_to_src    BIGINT
);
"""

COLUMNS = [
    "record_time", "flow_log_guid", "mac_address", "flow_log_resource",
    "target_resource", "acl_id", "rule_name", "timestamp_epoch_ms",
    "flow_time", "src_ip", "dst_ip", "src_port", "dst_port",
    "protocol", "direction", "state", "encryption",
    "packets_src_to_dst", "bytes_src_to_dst",
    "packets_dst_to_src", "bytes_dst_to_src",
]


def open_db(path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB database. None = in-memory."""
    db_path = str(path) if path else ":memory:"
    conn = duckdb.connect(db_path)
    conn.execute(SCHEMA_SQL)
    return conn


def load_records(conn: duckdb.DuckDBPyConnection, records: list[dict[str, Any]]) -> int:
    """Insert parsed flow log records into the flow_logs table. Returns row count.

    Uses DuckDB's native dict/list bulk insert for performance.
    """
    if not records:
        return 0

    # Build columnar dict for fast DuckDB ingestion
    data = {col: [rec.get(col) for rec in records] for col in COLUMNS}

    # Register as a temporary view and INSERT from it
    import pyarrow as pa

    # Convert to pyarrow table for zero-copy insert
    arrays = []
    for col in COLUMNS:
        arrays.append(pa.array(data[col]))
    table = pa.table({col: arr for col, arr in zip(COLUMNS, arrays)})

    conn.register("_temp_import", table)
    conn.execute(f"INSERT INTO flow_logs SELECT {', '.join(COLUMNS)} FROM _temp_import")
    conn.unregister("_temp_import")

    return len(records)


def get_row_count(conn: duckdb.DuckDBPyConnection) -> int:
    """Return the number of rows in flow_logs."""
    return conn.execute("SELECT COUNT(*) FROM flow_logs").fetchone()[0]
