"""List and download VNet flow log blobs from Azure Storage."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Actual blob path format observed in Azure:
# flowLogResourceID=/{SUB}_{RG}/{WATCHER}_{FLOWLOG}/y=2026/m=04/d=14/h=00/m=00/macAddress=.../PT1H.json
#
# Documentation claims a different format (year=, month=, etc.) so we support both.

# Regex patterns for both known path formats
_TIME_PATTERNS = [
    # Short format: y=YYYY/m=MM/d=DD/h=HH/m=MM (actual Azure format)
    re.compile(r"/y=(\d{4})/m=(\d{2})/d=(\d{2})/h=(\d{2})/m=(\d{2})"),
    # Long format: year=YYYY/month=MM/day=DD/hour=HH/minute=MM (documented format)
    re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})/hour=(\d{2})/minute=(\d{2})"),
]


def _blob_time(blob_name: str) -> datetime | None:
    """Extract the timestamp from a blob path, supporting both known path formats."""
    for pattern in _TIME_PATTERNS:
        match = pattern.search(blob_name)
        if match:
            y, mo, d, h, mi = (int(g) for g in match.groups())
            return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
    return None


def _discover_resource_prefixes(container: Any) -> list[str]:
    """Walk the top-level directory to discover flowLogResourceID prefixes."""
    prefixes = []
    # List blobs with a delimiter to get "directories" at top level
    for item in container.walk_blobs(delimiter="/"):
        if hasattr(item, "prefix") or (hasattr(item, "name") and item.name.endswith("/")):
            name = getattr(item, "prefix", None) or item.name
            if name.lower().startswith("flowlogresourceid="):
                prefixes.append(name)
            elif name.lower().startswith("resourceid="):
                prefixes.append(name)
    return prefixes


def _day_suffixes(start: datetime, end: datetime) -> list[str]:
    """Generate day-level path suffixes for both known formats."""
    suffixes = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=0)

    while current <= end_day:
        # Short format (actual Azure)
        suffixes.append(f"y={current.year}/m={current.month:02d}/d={current.day:02d}/")
        # Long format (documented)
        suffixes.append(f"year={current.year}/month={current.month:02d}/day={current.day:02d}/")
        current += timedelta(days=1)

    return suffixes


def _get_container(
    account_url: str,
    container_name: str,
    credential: Any = None,
    connection_string: str | None = None,
) -> Any:
    """Create a ContainerClient with the appropriate auth."""
    from azure.storage.blob import ContainerClient

    if connection_string:
        return ContainerClient.from_connection_string(connection_string, container_name)
    if credential:
        return ContainerClient(account_url, container_name, credential=credential)
    from azure.identity import DefaultAzureCredential
    return ContainerClient(account_url, container_name, credential=DefaultAzureCredential())


def list_flowlog_blobs(
    account_url: str,
    container_name: str,
    start: datetime,
    end: datetime,
    credential: Any = None,
    connection_string: str | None = None,
) -> list[str]:
    """List flow log blob names within a time range.

    Discovers resource prefixes automatically, then scans day-level paths.
    Auth priority: connection_string > credential > DefaultAzureCredential.
    """
    container = _get_container(account_url, container_name, credential, connection_string)

    # Step 1: Discover resource prefixes in the container
    resource_prefixes = _discover_resource_prefixes(container)
    if not resource_prefixes:
        # Fallback: maybe blobs start directly with year=/y=
        resource_prefixes = [""]
    logger.info("Discovered %d resource prefix(es)", len(resource_prefixes))

    # Step 2: For each resource prefix, walk into sub-levels to find the leaf
    # that contains y=YYYY or year=YYYY paths. We need to walk recursively since
    # the path can be: prefix/sub1/sub2/.../y=YYYY/...
    day_suffixes = _day_suffixes(start, end)
    matching: list[str] = []

    def _find_time_blobs(prefix: str) -> None:
        """Recursively walk into prefix until we find time-partitioned blobs."""
        # Try each day suffix appended to the current prefix
        for day_suffix in day_suffixes:
            search_prefix = prefix + day_suffix
            logger.debug("Searching prefix: %s", search_prefix)
            for blob in container.list_blobs(name_starts_with=search_prefix):
                if not blob.name.endswith(".json"):
                    continue
                blob_ts = _blob_time(blob.name)
                if blob_ts and start <= blob_ts <= end:
                    matching.append(blob.name)

        # If nothing found, walk one level deeper
        if not matching:
            for item in container.walk_blobs(name_starts_with=prefix, delimiter="/"):
                child = getattr(item, "prefix", None) or item.name
                if child == prefix or not child.endswith("/"):
                    continue
                # Only recurse into paths that look structural, not time paths
                segment = child[len(prefix):].rstrip("/")
                if re.match(r"(y|year)=\d", segment):
                    continue  # Already tried via day_suffixes
                _find_time_blobs(child)
                if matching:
                    return  # Found blobs, stop recursing

    for rp in resource_prefixes:
        _find_time_blobs(rp)

    logger.info("Found %d blobs in time range", len(matching))
    return sorted(matching)


def download_and_parse_blob(
    account_url: str,
    container_name: str,
    blob_name: str,
    credential: Any = None,
    connection_string: str | None = None,
) -> list[dict[str, Any]]:
    """Download a single blob and parse it into flow records."""
    from azure.storage.blob import BlobClient
    from flowloganalysis.parser import parse_flowlog_json

    if connection_string:
        client = BlobClient.from_connection_string(connection_string, container_name, blob_name)
    elif credential:
        client = BlobClient(account_url, container_name, blob_name, credential=credential)
    else:
        from azure.identity import DefaultAzureCredential
        client = BlobClient(account_url, container_name, blob_name, credential=DefaultAzureCredential())

    logger.debug("Downloading blob: %s", blob_name)
    data = client.download_blob().readall()
    doc = json.loads(data)
    records = parse_flowlog_json(doc)
    logger.debug("Parsed %d records from %s", len(records), blob_name)
    return records


def download_all_blobs(
    account_url: str,
    container_name: str,
    blob_names: list[str],
    credential: Any = None,
    connection_string: str | None = None,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """Download and parse multiple blobs in parallel."""
    all_records: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                download_and_parse_blob,
                account_url, container_name, name, credential, connection_string,
            ): name
            for name in blob_names
        }
        for future in as_completed(futures):
            blob_name = futures[future]
            try:
                records = future.result()
                all_records.extend(records)
                logger.info("Loaded %d records from %s", len(records), blob_name)
            except Exception:
                logger.exception("Failed to process blob: %s", blob_name)

    return all_records
