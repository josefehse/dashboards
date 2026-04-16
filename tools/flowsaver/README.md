# Azure VNet Flow Log Analysis

Parse and analyze Azure VNet flow logs using Azure Data Explorer (ADX) free tier. Ingests flow log JSON from blob storage, auto-transforms it into a searchable table, and provides dashboard queries for troubleshooting.

## Architecture

```
Azure Blob Storage          ADX Free Tier                     Workbook / Dashboard
(flow log JSON files)  -->  flowlogsraw (raw JSON landing)    (KQL queries)
                            --> FlowLogExpand() function
                            --> flowlogs (parsed, searchable)
```

Flow log JSON files contain nested records with CSV-encoded flow tuples. The ADX **update policy** automatically expands these into flat rows with fields like `SrcIP`, `DstIP`, `DstPort`, `Protocol`, `BytesSrcToDst`, etc.

## Prerequisites

- **Azure Data Explorer free cluster** — create one at [dataexplorer.azure.com](https://dataexplorer.azure.com)
- **Python 3.10+** — for the CLI tool that generates ingestion commands
- **Azure Storage account** — containing VNet flow logs (container: `insights-logs-flowlogflowevent`)
- **SAS token** — with read access to the flow log container

## Setup

### Step 1: Create the ADX cluster and database

1. Go to [dataexplorer.azure.com](https://dataexplorer.azure.com)
2. Create a free cluster (or use an existing one)
3. Create a database called `flowlogs` (or any name you prefer)

### Step 2: Run the ADX setup script

Open `adx-setup.kql` in the ADX Web UI query editor and **run the entire block**. It uses `.execute database script` to create everything in one go:

- `flowlogsraw` — raw JSON landing table (1-day auto-cleanup)
- `FlowLogMapping` — JSON ingestion mapping
- `flowlogs` — parsed/searchable table with all flow fields
- `FlowLogExpand()` — KQL function that expands nested JSON + CSV tuples
- Update policy that auto-triggers the function on ingestion

After running, verify the mapping exists:

```kql
.show table flowlogsraw ingestion json mappings
```

### Step 3: Install the CLI tool

```bash
pip install -e ".[azure]"
```

> [!NOTE]
> **Azure Cloud Shell:** If running inside Azure Cloud Shell (or any containerized environment), add `--user` to avoid permission errors: `pip install -e ".[azure]" --user`

This installs the `flowlog` CLI with Azure Storage SDK support.

### Step 4: Generate and run ingestion commands

The CLI lists blobs in your storage account for a time range and outputs ready-to-paste KQL `.ingest` commands.

#### Ingest last 4 hours

<details open>
<summary>Bash</summary>

```bash
flowlog generate-kql \
  --storage-account <YOUR_STORAGE_ACCOUNT> \
  --container insights-logs-flowlogflowevent \
  --last-hours 4 \
  --sas-token "<YOUR_SAS_TOKEN>"
```

</details>

<details>
<summary>PowerShell</summary>

```powershell
flowlog generate-kql `
  --storage-account <YOUR_STORAGE_ACCOUNT> `
  --container insights-logs-flowlogflowevent `
  --last-hours 4 `
  --sas-token "<YOUR_SAS_TOKEN>"
```

</details>

#### Ingest last 2 days

<details open>
<summary>Bash</summary>

```bash
flowlog generate-kql \
  --storage-account <YOUR_STORAGE_ACCOUNT> \
  --container insights-logs-flowlogflowevent \
  --last 2 \
  --sas-token "<YOUR_SAS_TOKEN>"
```

</details>

<details>
<summary>PowerShell</summary>

```powershell
flowlog generate-kql `
  --storage-account <YOUR_STORAGE_ACCOUNT> `
  --container insights-logs-flowlogflowevent `
  --last 2 `
  --sas-token "<YOUR_SAS_TOKEN>"
```

</details>

#### Ingest a specific time range

<details open>
<summary>Bash</summary>

```bash
flowlog generate-kql \
  --storage-account <YOUR_STORAGE_ACCOUNT> \
  --container insights-logs-flowlogflowevent \
  --start 2026-04-14T00:00 --end 2026-04-14T12:00 \
  --sas-token "<YOUR_SAS_TOKEN>"
```

</details>

<details>
<summary>PowerShell</summary>

```powershell
flowlog generate-kql `
  --storage-account <YOUR_STORAGE_ACCOUNT> `
  --container insights-logs-flowlogflowevent `
  --start 2026-04-14T00:00 --end 2026-04-14T12:00 `
  --sas-token "<YOUR_SAS_TOKEN>"
```

</details>

Copy the output `.ingest` command from the generated `.kql` file (e.g. `ingest-20260414-160000.kql`), paste it into the ADX Web UI query editor, and run it. The update policy will automatically parse the raw JSON into the `flowlogs` table.

### Step 5: Verify ingestion

```kql
flowlogsraw | count
flowlogs | count
flowlogs | take 10
```

## Querying

Once data is ingested, query the `flowlogs` table directly in the ADX Web UI:

```kql
// All flows from a specific source
flowlogs | where SrcIP == "10.0.0.4"

// All blocked flows (Begin state with 0 bytes transferred)
flowlogs | where State == "Begin" and BytesSrcToDst == 0 and BytesDstToSrc == 0

// Top destinations by traffic volume
flowlogs
| summarize TotalBytes = sum(BytesSrcToDst + BytesDstToSrc) by DstIP, DstPort
| top 10 by TotalBytes desc

// Traffic over time
flowlogs
| summarize Bytes = sum(BytesSrcToDst + BytesDstToSrc), Flows = count() by bin(FlowTime, 5m)
| render timechart

// All flows on a specific port
flowlogs | where DstPort == 443 | take 100
```

## Dashboards

### ADX Dashboard (recommended)

Use the queries in `adx-dashboard-queries.kql` to build a dashboard in the ADX Web UI:

1. Go to [dataexplorer.azure.com](https://dataexplorer.azure.com) → **Dashboards** → **New Dashboard**
2. Add parameters: `_startTime` (DateTime), `_endTime` (DateTime), plus optional `SrcIP`, `DstIP`, `DstPort` multi-select dropdowns
3. Add tiles using the queries from `adx-dashboard-queries.kql`

### Azure Monitor Workbook

Import `workbook-flowlogs.json` into Azure Monitor:

1. Azure Portal → **Monitor** → **Workbooks** → **New** → **Advanced Editor** (code icon `</>`)
2. Paste the contents of `workbook-flowlogs.json`
3. Click **Apply**, then fill in the **Cluster Name** and **Database Name** parameters at the top

## Parsed Table Schema

| Column | Type | Description |
|---|---|---|
| `RecordTime` | datetime | When the flow log record was generated |
| `FlowTime` | datetime | When the individual flow was observed |
| `SrcIP` | string | Source IP address |
| `DstIP` | string | Destination IP address |
| `SrcPort` | int | Source port |
| `DstPort` | int | Destination port |
| `Protocol` | string | TCP or UDP |
| `Direction` | string | Inbound or Outbound |
| `State` | string | Begin, Continuing, or End |
| `Encryption` | string | Encryption state |
| `PacketsSrcToDst` | long | Packets from source to destination |
| `BytesSrcToDst` | long | Bytes from source to destination |
| `PacketsDstToSrc` | long | Packets from destination to source |
| `BytesDstToSrc` | long | Bytes from destination to source |
| `RuleName` | string | NSG rule that matched |
| `AclID` | string | ACL identifier |
| `MacAddress` | string | MAC address of the NIC |
| `FlowLogResource` | string | Flow log resource ID |
| `TargetResource` | string | Target resource (VNet/subnet/NIC) |

## Cleanup

Both tables have short retention policies set by `adx-setup.kql` (`flowlogsraw` = 1 day, `flowlogs` = 2 days), so data auto-purges. For immediate cleanup, copy-paste `adx-clear.kql` into the ADX query editor and run it.

**To adjust retention:**

```kql
// Change parsed data retention (e.g., 7 days)
.alter-merge table flowlogs policy retention softdelete = 7d
```

**To drop everything and start fresh:**

```kql
.drop table flowlogs ifexists
.drop table flowlogsraw ifexists
.drop function FlowLogExpand ifexists
```

Then re-run `adx-setup.kql` when you need it again.

## Files

| File | Purpose |
|---|---|
| `adx-setup.kql` | One-shot ADX schema setup (run once per cluster) |
| `adx-clear.kql` | Clear all ingested data (keeps schema for re-use) |
| `adx-dashboard-queries.kql` | KQL queries for building an ADX dashboard |
| `workbook-flowlogs.json` | Azure Monitor Workbook template (importable) |
| `New-FlowlogCommand.ps1` | PowerShell helper: browse storage accounts, generate SAS + commands |
| `src/flowloganalysis/cli.py` | CLI tool (`flowlog` command) |
| `src/flowloganalysis/parser.py` | VNet flow log JSON parser |
| `src/flowloganalysis/storage.py` | Azure blob listing with time-range filtering |

## SAS Token

The easiest way to generate a SAS token is with the helper script:

```powershell
# Interactive: browse storage accounts, auto-generate 60-min SAS token
.\New-FlowlogCommand.ps1

# Search all subscriptions, last 12 hours
.\New-FlowlogCommand.ps1 -AllSubscriptions -LastHours 12

# Specific subscription, last 2 days
.\New-FlowlogCommand.ps1 -Subscription "My Subscription" -LastDays 2
```

The script outputs ready-to-paste commands for both Bash and PowerShell, and copies the PowerShell version to your clipboard.

### Manual SAS Token

To generate a SAS token manually via the Azure Portal:

1. Azure Portal → Storage Account → **Shared access signature**
2. Permissions: **Read** + **List**
3. Allowed resource types: **Container** + **Object**
4. Set an expiry date
5. Click **Generate SAS and connection string**
6. Copy the **SAS token** (starts with `sp=r&st=...`)

Pass it to the CLI via `--sas-token` (without the leading `?`).
