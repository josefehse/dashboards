"""CLI entrypoint for flow log analysis."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


MAX_INGEST_DAYS = 7


def _parse_time(value: str) -> datetime:
    """Parse a datetime string in ISO-like format, assume UTC if no tz."""
    for fmt in [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Cannot parse datetime: {value}")


def _resolve_time_range(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Resolve --start/--end, --last (days), or --last-hours into a (start, end) pair."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    last_days = getattr(args, "last", None)
    last_hours = getattr(args, "last_hours", None)
    start = getattr(args, "start", None)
    end = getattr(args, "end", None)

    if last_hours is not None:
        if last_hours < 1 or last_hours > MAX_INGEST_DAYS * 24:
            print(f"Error: --last-hours must be between 1 and {MAX_INGEST_DAYS * 24}", file=sys.stderr)
            sys.exit(1)
        return now - timedelta(hours=last_hours), now

    if last_days is not None:
        if last_days < 1 or last_days > MAX_INGEST_DAYS:
            print(f"Error: --last must be between 1 and {MAX_INGEST_DAYS}", file=sys.stderr)
            sys.exit(1)
        return now - timedelta(days=last_days), now

    if not start and not end:
        print("Error: specify --start/--end, --last N, or --last-hours N", file=sys.stderr)
        sys.exit(1)

    if end and not start:
        print("Error: --end requires --start", file=sys.stderr)
        sys.exit(1)

    if not end:
        end = now

    span = end - start
    if span.total_seconds() < 0:
        print("Error: --start must be before --end", file=sys.stderr)
        sys.exit(1)
    if span.days > MAX_INGEST_DAYS:
        print(f"Error: time range exceeds {MAX_INGEST_DAYS} days ({span.days} days).", file=sys.stderr)
        sys.exit(1)

    return start, end


def cmd_ingest_local(args: argparse.Namespace) -> None:
    """Ingest flow log JSON files from local disk."""
    from flowloganalysis.parser import parse_flowlog_file
    from flowloganalysis.loader import open_db, load_records, get_row_count

    db_path = args.db or "flowlogs.duckdb"
    conn = open_db(db_path)
    total = 0

    for file_path in args.files:
        p = Path(file_path)
        if not p.exists():
            print(f"Warning: {p} not found, skipping", file=sys.stderr)
            continue
        print(f"Parsing {p}...")
        records = parse_flowlog_file(p)
        loaded = load_records(conn, records)
        total += loaded
        print(f"  Loaded {loaded} flow records")

    print(f"\nTotal: {total} records loaded into {db_path}")
    print(f"Database now has {get_row_count(conn)} total records")
    conn.close()


def cmd_ingest_azure(args: argparse.Namespace) -> None:
    """Ingest flow logs from Azure Storage."""
    from flowloganalysis.storage import list_flowlog_blobs, download_all_blobs
    from flowloganalysis.loader import open_db, load_records, get_row_count

    account_url = f"https://{args.storage_account}.blob.core.windows.net"
    container = args.container
    conn_str = args.connection_string
    start, end = _resolve_time_range(args)
    db_path = args.db or "flowlogs.duckdb"

    credential = None
    if not conn_str:
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
        except ImportError:
            print("Error: azure-identity not installed. Use --connection-string or install with: pip install flowloganalysis[azure]", file=sys.stderr)
            sys.exit(1)

    print(f"Listing blobs from {args.storage_account}/{container} ({start} to {end})...")
    blobs = list_flowlog_blobs(account_url, container, start, end, credential, conn_str)
    print(f"Found {len(blobs)} blobs")

    if not blobs:
        print("No flow log blobs found in the specified time range.")
        return

    print(f"Downloading and parsing {len(blobs)} blobs...")
    all_records = download_all_blobs(
        account_url, container, blobs, credential, conn_str, max_workers=args.workers
    )

    conn = open_db(db_path)
    loaded = load_records(conn, all_records)
    print(f"\nTotal: {loaded} records loaded into {db_path}")
    print(f"Database now has {get_row_count(conn)} total records")
    conn.close()


def cmd_shell(args: argparse.Namespace) -> None:
    """Open an interactive DuckDB SQL shell."""
    import duckdb

    db_path = args.db or "flowlogs.duckdb"
    if not Path(db_path).exists():
        print(f"Database {db_path} not found. Run 'flowlog ingest' first.", file=sys.stderr)
        sys.exit(1)

    conn = duckdb.connect(db_path, read_only=True)
    row_count = conn.execute("SELECT COUNT(*) FROM flow_logs").fetchone()[0]
    print(f"Connected to {db_path} ({row_count} flow records)")
    print("Type SQL queries, or 'exit' to quit.\n")

    while True:
        try:
            query = input("flowlog> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query or query.lower() in ("exit", "quit", "\\q"):
            break
        try:
            result = conn.execute(query)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            if rows:
                # Print as a formatted table
                col_widths = [len(c) for c in columns]
                for row in rows:
                    for i, val in enumerate(row):
                        col_widths[i] = max(col_widths[i], len(str(val)))

                header = " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(columns))
                print(header)
                print("-+-".join("-" * w for w in col_widths))
                for row in rows:
                    print(" | ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)))
                print(f"\n({len(rows)} rows)")
            else:
                print("(0 rows)")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

    conn.close()


def cmd_query(args: argparse.Namespace) -> None:
    """Run a filtered query against the database."""
    import duckdb

    db_path = args.db or "flowlogs.duckdb"
    if not Path(db_path).exists():
        print(f"Database {db_path} not found. Run 'flowlog ingest' first.", file=sys.stderr)
        sys.exit(1)

    conditions = []
    params = []

    if args.src:
        conditions.append("src_ip = ?")
        params.append(args.src)
    if args.dst:
        conditions.append("dst_ip = ?")
        params.append(args.dst)
    if args.src_port:
        conditions.append("src_port = ?")
        params.append(args.src_port)
    if args.dst_port:
        conditions.append("dst_port = ?")
        params.append(args.dst_port)
    if args.protocol:
        conditions.append("protocol = ?")
        params.append(args.protocol)
    if args.direction:
        conditions.append("direction = ?")
        params.append(args.direction)
    if args.state:
        conditions.append("state = ?")
        params.append(args.state)
    if args.start:
        conditions.append("flow_time >= ?")
        params.append(args.start)
    if args.end:
        conditions.append("flow_time <= ?")
        params.append(args.end)

    where = " AND ".join(conditions) if conditions else "1=1"
    limit = args.limit or 50

    conn = duckdb.connect(db_path, read_only=True)
    query = f"SELECT flow_time, src_ip, dst_ip, src_port, dst_port, protocol, direction, state, bytes_src_to_dst, bytes_dst_to_src, rule_name FROM flow_logs WHERE {where} ORDER BY flow_time LIMIT {limit}"

    result = conn.execute(query, params)
    columns = [desc[0] for desc in result.description]
    rows = result.fetchall()

    if rows:
        col_widths = [len(c) for c in columns]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val)))

        header = " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(columns))
        print(header)
        print("-+-".join("-" * w for w in col_widths))
        for row in rows:
            print(" | ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)))
        print(f"\n({len(rows)} rows)")
    else:
        print("No matching flows found.")

    conn.close()


def cmd_summary(args: argparse.Namespace) -> None:
    """Show summary statistics."""
    import duckdb

    db_path = args.db or "flowlogs.duckdb"
    if not Path(db_path).exists():
        print(f"Database {db_path} not found.", file=sys.stderr)
        sys.exit(1)

    conn = duckdb.connect(db_path, read_only=True)

    total = conn.execute("SELECT COUNT(*) FROM flow_logs").fetchone()[0]
    time_range = conn.execute("SELECT MIN(flow_time), MAX(flow_time) FROM flow_logs").fetchone()
    print(f"Total flow records: {total}")
    print(f"Time range: {time_range[0]} → {time_range[1]}")
    print()

    print("— By protocol —")
    for row in conn.execute("SELECT protocol, COUNT(*) as cnt FROM flow_logs GROUP BY protocol ORDER BY cnt DESC").fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\n— By direction —")
    for row in conn.execute("SELECT direction, COUNT(*) as cnt FROM flow_logs GROUP BY direction ORDER BY cnt DESC").fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\n— By state —")
    for row in conn.execute("SELECT state, COUNT(*) as cnt FROM flow_logs GROUP BY state ORDER BY cnt DESC").fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\n— Top 10 destinations by bytes received —")
    for row in conn.execute("""
        SELECT dst_ip, dst_port,
               SUM(bytes_src_to_dst) as bytes_sent,
               SUM(bytes_dst_to_src) as bytes_received,
               COUNT(*) as flows
        FROM flow_logs
        GROUP BY dst_ip, dst_port
        ORDER BY bytes_sent DESC
        LIMIT 10
    """).fetchall():
        print(f"  {row[0]}:{row[1]}  sent={row[2]:,}B  recv={row[3]:,}B  flows={row[4]}")

    print("\n— Top 10 sources by bytes sent —")
    for row in conn.execute("""
        SELECT src_ip,
               SUM(bytes_src_to_dst) as bytes_sent,
               SUM(bytes_dst_to_src) as bytes_received,
               COUNT(*) as flows
        FROM flow_logs
        GROUP BY src_ip
        ORDER BY bytes_sent DESC
        LIMIT 10
    """).fetchall():
        print(f"  {row[0]}  sent={row[1]:,}B  recv={row[2]:,}B  flows={row[3]}")

    conn.close()


def cmd_generate_kql(args: argparse.Namespace) -> None:
    """Generate KQL .ingest commands for blobs in a time range."""
    from flowloganalysis.storage import list_flowlog_blobs

    account_url = f"https://{args.storage_account}.blob.core.windows.net"
    container = args.container
    sas_token = args.sas_token
    conn_str = args.connection_string
    start, end = _resolve_time_range(args)
    table = args.table or "flowlogsraw"

    credential = None
    if not conn_str:
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
        except ImportError:
            print("Error: azure-identity not installed. Use --connection-string or install with: pip install flowloganalysis[azure]", file=sys.stderr)
            sys.exit(1)

    print(f"// Listing blobs: {args.storage_account}/{container}", file=sys.stderr)
    print(f"// Time range: {start} → {end}", file=sys.stderr)
    blobs = list_flowlog_blobs(account_url, container, start, end, credential, conn_str)
    print(f"// Found {len(blobs)} blobs", file=sys.stderr)

    if not blobs:
        print("// No blobs found in the specified time range.", file=sys.stderr)
        return

    sas = sas_token if sas_token else "<PASTE_SAS_TOKEN_HERE>"

    lines = []
    lines.append(f"// Auto-generated: {len(blobs)} blobs, {start} → {end}")
    lines.append(f".ingest into table {table} (")
    for i, blob in enumerate(blobs):
        sep = "," if i < len(blobs) - 1 else ""
        lines.append(f"    h'{account_url}/{container}/{blob}?{sas}'{sep}")
    lines.append(") with (format='multijson', ingestionMappingReference='FlowLogMapping')")

    # Write to a datetime-stamped .kql file
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"ingest-{timestamp}.kql"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Generated {filename} ({len(blobs)} blobs)", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flowlog",
        description="Azure VNet Flow Log Analysis Tool",
    )
    parser.add_argument("--db", help="DuckDB database path (default: flowlogs.duckdb)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command")

    # ingest-local
    p_local = sub.add_parser("ingest-local", help="Ingest flow log JSON files from disk")
    p_local.add_argument("files", nargs="+", help="JSON flow log file paths")

    # ingest
    p_azure = sub.add_parser("ingest", help="Ingest flow logs from Azure Storage")
    p_azure.add_argument("--storage-account", required=True, help="Storage account name")
    p_azure.add_argument("--container", required=True, help="Blob container name")
    p_azure.add_argument("--connection-string", help="Storage connection string (alternative to DefaultAzureCredential)")
    time_group = p_azure.add_mutually_exclusive_group(required=True)
    time_group.add_argument("--last", type=int, metavar="DAYS", help="Ingest last N days (max 7)")
    time_group.add_argument("--start", type=_parse_time, help="Start time (e.g. 2026-04-14T00:00)")
    p_azure.add_argument("--end", type=_parse_time, help="End time (e.g. 2026-04-14T12:00). Defaults to now if omitted.")
    p_azure.add_argument("--workers", type=int, default=4, help="Parallel download threads (default: 4)")

    # shell
    sub.add_parser("shell", help="Interactive SQL shell")

    # query
    p_query = sub.add_parser("query", help="Filter and search flow logs")
    p_query.add_argument("--src", help="Source IP")
    p_query.add_argument("--dst", help="Destination IP")
    p_query.add_argument("--src-port", type=int, help="Source port")
    p_query.add_argument("--dst-port", type=int, help="Destination port")
    p_query.add_argument("--protocol", choices=["TCP", "UDP"], help="Protocol")
    p_query.add_argument("--direction", choices=["Inbound", "Outbound"], help="Direction")
    p_query.add_argument("--state", choices=["Begin", "Continuing", "End"], help="Flow state")
    p_query.add_argument("--start", type=_parse_time, help="Start time filter")
    p_query.add_argument("--end", type=_parse_time, help="End time filter")
    p_query.add_argument("--limit", type=int, default=50, help="Max rows (default: 50)")

    # summary
    sub.add_parser("summary", help="Show summary statistics")

    # generate-kql
    p_kql = sub.add_parser("generate-kql", help="Generate KQL .ingest commands for a time range")
    p_kql.add_argument("--storage-account", required=True, help="Storage account name")
    p_kql.add_argument("--container", required=True, help="Blob container name")
    p_kql.add_argument("--connection-string", help="Storage connection string")
    p_kql.add_argument("--sas-token", help="SAS token to embed in the generated URLs (without leading ?)")
    p_kql.add_argument("--table", default="flowlogsraw", help="Target ADX table (default: flowlogsraw)")
    kql_time = p_kql.add_mutually_exclusive_group(required=True)
    kql_time.add_argument("--last", type=int, metavar="DAYS", help="Last N days (max 7)")
    kql_time.add_argument("--last-hours", type=int, metavar="HOURS", help="Last N hours")
    kql_time.add_argument("--start", type=_parse_time, help="Start time (e.g. 2026-04-14T00:00)")
    p_kql.add_argument("--end", type=_parse_time, help="End time (defaults to now)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        # Suppress noisy Azure SDK logging unless verbose
        logging.getLogger("azure").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    commands = {
        "ingest-local": cmd_ingest_local,
        "ingest": cmd_ingest_azure,
        "shell": cmd_shell,
        "query": cmd_query,
        "summary": cmd_summary,
        "generate-kql": cmd_generate_kql,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
