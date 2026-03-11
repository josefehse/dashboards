# Log Analytics Table Retention Tool

A PowerShell script to manage Interactive (Analytics) Retention and Total Retention settings across tables in a Log Analytics workspace.

## Features

- **Report mode** — list current retention settings for all tables without making changes
- **Bulk update** — apply default retention values to all tables at once
- **Per-table overrides** — provide a CSV file with specific retention values for individual tables
- **Table filtering** — use wildcard patterns to target specific tables (e.g., `Security*`)
- **Confirmation prompts** — approve changes per table, apply all remaining, or quit
- **Summary export** — outputs a CSV report of all changes made

## Prerequisites

- Azure PowerShell module (`Az.Accounts` for `Set-AzContext` and `Invoke-AzRestMethod`)
- Authenticated Azure session (`Connect-AzAccount`)
- Permissions: `Microsoft.OperationalInsights/workspaces/tables/write` on the workspace

## Usage

### Report current retention

```powershell
.\Set-TableRetention.ps1 `
    -SubscriptionId "00000000-0000-0000-0000-000000000000" `
    -ResourceGroupName "my-rg" `
    -WorkspaceName "my-workspace" `
    -ReportOnly
```

### Set default retention for all tables

```powershell
.\Set-TableRetention.ps1 `
    -SubscriptionId "00000000-0000-0000-0000-000000000000" `
    -ResourceGroupName "my-rg" `
    -WorkspaceName "my-workspace" `
    -InteractiveRetentionDays 90 `
    -TotalRetentionDays 365
```

### Set defaults with per-table overrides

```powershell
.\Set-TableRetention.ps1 `
    -SubscriptionId "00000000-0000-0000-0000-000000000000" `
    -ResourceGroupName "my-rg" `
    -WorkspaceName "my-workspace" `
    -InteractiveRetentionDays 30 `
    -TotalRetentionDays 180 `
    -OverrideCsvPath ".\sample-overrides.csv"
```

### Filter to specific tables

```powershell
.\Set-TableRetention.ps1 `
    -SubscriptionId "00000000-0000-0000-0000-000000000000" `
    -ResourceGroupName "my-rg" `
    -WorkspaceName "my-workspace" `
    -InteractiveRetentionDays 90 `
    -TotalRetentionDays 365 `
    -TableFilter "Security*"
```

## Override CSV Format

The CSV file must have these columns:

| Column | Description |
|--------|-------------|
| `TableName` | Exact name of the table (e.g., `SecurityEvent`) |
| `InteractiveRetentionDays` | Interactive (Analytics) retention in days (4–730) |
| `TotalRetentionDays` | Total retention in days (must be ≥ Interactive, max 4383) |

See `sample-overrides.csv` for an example.

## Confirmation Prompts

When applying changes, you are prompted for each table:

- **y** — apply changes to this table
- **n** — skip this table
- **a** — apply changes to this and all remaining tables
- **q** — quit without making further changes

## Output

After execution, a summary CSV is saved in the current directory with a timestamped filename (e.g., `retention-update-20260310-153000.csv`).

## Files

| File | Description |
|------|-------------|
| `Set-TableRetention.ps1` | The retention management script |
| `sample-overrides.csv` | Example per-table override CSV |

