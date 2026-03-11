<#
.SYNOPSIS
    Manage Log Analytics workspace table retention settings.

.DESCRIPTION
    Lists tables in a Log Analytics workspace and updates their Interactive (Analytics)
    Retention and Total Retention periods. Supports a default retention for all tables
    with optional per-table overrides via a CSV file.

.PARAMETER SubscriptionId
    Azure subscription ID containing the workspace.

.PARAMETER ResourceGroupName
    Resource group containing the workspace.

.PARAMETER WorkspaceName
    Name of the Log Analytics workspace.

.PARAMETER InteractiveRetentionDays
    Default Interactive (Analytics) Retention in days to apply to all tables.
    Minimum 4 days, maximum 730 days.

.PARAMETER TotalRetentionDays
    Default Total Retention in days to apply to all tables.
    Must be >= InteractiveRetentionDays. Maximum 4383 days (12 years).

.PARAMETER OverrideCsvPath
    Optional path to a CSV file with per-table retention overrides.
    Expected columns: TableName, InteractiveRetentionDays, TotalRetentionDays.
    Tables listed here will use their CSV values instead of the defaults.

.PARAMETER TableFilter
    Optional wildcard pattern to filter which tables to process (e.g., "Security*").
    Defaults to "*" (all tables).

.PARAMETER SkipBasicLogsTables
    If set, skips tables configured with the BasicLogs plan.

.PARAMETER ActiveOnly
    If set, only includes tables that have actually ingested data.
    Runs a query against the workspace to discover active tables.

.PARAMETER ReportOnly
    If set, only lists current retention settings without making changes.

.EXAMPLE
    # Report current retention for all tables
    .\Set-TableRetention.ps1 -SubscriptionId "xxx" -ResourceGroupName "rg" -WorkspaceName "law" -ReportOnly

.EXAMPLE
    # Set all tables to 90 days interactive, 365 days total
    .\Set-TableRetention.ps1 -SubscriptionId "xxx" -ResourceGroupName "rg" -WorkspaceName "law" `
        -InteractiveRetentionDays 90 -TotalRetentionDays 365

.EXAMPLE
    # Set defaults with per-table overrides from CSV
    .\Set-TableRetention.ps1 -SubscriptionId "xxx" -ResourceGroupName "rg" -WorkspaceName "law" `
        -InteractiveRetentionDays 30 -TotalRetentionDays 180 -OverrideCsvPath ".\overrides.csv"
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$WorkspaceName,

    [Parameter(Mandatory = $false)]
    [ValidateRange(4, 730)]
    [int]$InteractiveRetentionDays,

    [Parameter(Mandatory = $false)]
    [ValidateRange(4, 4383)]
    [int]$TotalRetentionDays,

    [Parameter(Mandatory = $false)]
    [string]$OverrideCsvPath,

    [Parameter(Mandatory = $false)]
    [string]$TableFilter = "*",

    [Parameter(Mandatory = $false)]
    [switch]$SkipBasicLogsTables,

    [Parameter(Mandatory = $false)]
    [switch]$ActiveOnly,

    [Parameter(Mandatory = $false)]
    [switch]$ReportOnly
)

$ErrorActionPreference = "Stop"

# --- Validation ---
if (-not $ReportOnly) {
    if (-not $PSBoundParameters.ContainsKey('InteractiveRetentionDays') -and -not $OverrideCsvPath) {
        Write-Error "You must specify -InteractiveRetentionDays and -TotalRetentionDays, or provide -OverrideCsvPath, or use -ReportOnly."
        return
    }
    if ($PSBoundParameters.ContainsKey('InteractiveRetentionDays') -and -not $PSBoundParameters.ContainsKey('TotalRetentionDays')) {
        Write-Error "When specifying -InteractiveRetentionDays, you must also specify -TotalRetentionDays."
        return
    }
    if ($PSBoundParameters.ContainsKey('TotalRetentionDays') -and $TotalRetentionDays -lt $InteractiveRetentionDays) {
        Write-Error "TotalRetentionDays ($TotalRetentionDays) must be >= InteractiveRetentionDays ($InteractiveRetentionDays)."
        return
    }
}

# --- Load CSV overrides ---
$overrides = @{}
if ($OverrideCsvPath) {
    if (-not (Test-Path $OverrideCsvPath)) {
        Write-Error "Override CSV file not found: $OverrideCsvPath"
        return
    }
    $csvData = Import-Csv $OverrideCsvPath
    foreach ($row in $csvData) {
        if (-not $row.TableName -or -not $row.InteractiveRetentionDays -or -not $row.TotalRetentionDays) {
            Write-Warning "Skipping invalid CSV row: $($row | ConvertTo-Json -Compress)"
            continue
        }
        $csvInteractive = [int]$row.InteractiveRetentionDays
        $csvTotal = [int]$row.TotalRetentionDays
        if ($csvTotal -lt $csvInteractive) {
            Write-Warning "CSV override for '$($row.TableName)': TotalRetentionDays ($csvTotal) < InteractiveRetentionDays ($csvInteractive). Skipping."
            continue
        }
        $overrides[$row.TableName] = @{
            InteractiveRetentionDays = $csvInteractive
            TotalRetentionDays       = $csvTotal
        }
    }
    Write-Host "Loaded $($overrides.Count) table override(s) from CSV." -ForegroundColor Cyan
}

# --- Connect and set context ---
Write-Host "`nSetting subscription context to: $SubscriptionId" -ForegroundColor Cyan
Set-AzContext -SubscriptionId $SubscriptionId | Out-Null

# --- Build API path ---
$apiVersion = "2023-09-01"
$basePath = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.OperationalInsights/workspaces/$WorkspaceName"

# --- List all tables ---
Write-Host "Fetching tables from workspace '$WorkspaceName'..." -ForegroundColor Cyan
$tablesResponse = Invoke-AzRestMethod -Method GET -Path "$basePath/tables?api-version=$apiVersion"
if ($tablesResponse.StatusCode -ne 200) {
    Write-Error "Failed to list tables. Status: $($tablesResponse.StatusCode). Response: $($tablesResponse.Content)"
    return
}

$tables = ($tablesResponse.Content | ConvertFrom-Json).value

# --- Filter tables ---
$filteredTables = $tables | Where-Object { $_.name -like $TableFilter }
if ($SkipBasicLogsTables) {
    $filteredTables = $filteredTables | Where-Object { $_.properties.plan -ne "Basic" }
}

# --- Filter to tables with data (ActiveOnly) ---
if ($ActiveOnly) {
    Write-Host "Querying workspace metadata for tables with data..." -ForegroundColor Cyan

    # Always include custom tables (they were explicitly created)
    $customTableNames = @(($filteredTables | Where-Object { $_.properties.schema.tableType -eq "CustomLog" }).name)

    # Call the Log Analytics metadata endpoint to get tables with hasData flag
    $activeTableNames = @()
    try {
        $metadataUrl = "https://api.loganalytics.io/v1/subscriptions/$SubscriptionId/resourcegroups/$ResourceGroupName/providers/microsoft.operationalinsights/workspaces/$WorkspaceName/metadata"
        $tokenObj = Get-AzAccessToken -ResourceUrl "https://api.loganalytics.io"
        # Handle both old (string) and new (SecureString) Az module token formats
        if ($tokenObj.Token -is [System.Security.SecureString]) {
            $tokenStr = [System.Net.NetworkCredential]::new('', $tokenObj.Token).Password
        }
        else {
            $tokenStr = $tokenObj.Token
        }
        $headers = @{
            Authorization  = "Bearer $tokenStr"
            "Content-Type" = "application/json"
            "prefer"       = "metadata-format-v4, wait=600"
        }
        $metaResponse = Invoke-RestMethod -Uri $metadataUrl -Method POST -Headers $headers -Body "{}" -ErrorAction Stop
        $activeTableNames = @($metaResponse.tables | Where-Object { $_.hasData -eq $true } | ForEach-Object { $_.name })
        Write-Host "Found $($activeTableNames.Count) table(s) with data via metadata API." -ForegroundColor Cyan
    }
    catch {
        Write-Warning "Failed to query metadata API: $_"
        Write-Warning "Falling back to custom tables only."
    }

    # Combine: tables with hasData + custom tables
    $allActiveNames = @($activeTableNames) + @($customTableNames) | Select-Object -Unique
    $filteredTables = $filteredTables | Where-Object { $_.name -in $allActiveNames }
    Write-Host "Filtered to $($filteredTables.Count) active table(s)." -ForegroundColor Cyan
}

$filteredTables = $filteredTables | Sort-Object name

Write-Host "Found $($filteredTables.Count) table(s) matching filter '$TableFilter'." -ForegroundColor Cyan

# --- Report / Update ---
$results = @()

foreach ($table in $filteredTables) {
    $tableName = $table.name
    $props = $table.properties
    $currentInteractive = $props.retentionInDays
    $currentTotal = $props.totalRetentionInDays
    $plan = $props.plan

    # Determine target retention
    if ($overrides.ContainsKey($tableName)) {
        $targetInteractive = $overrides[$tableName].InteractiveRetentionDays
        $targetTotal = $overrides[$tableName].TotalRetentionDays
        $source = "CSV Override"
    }
    elseif ($PSBoundParameters.ContainsKey('InteractiveRetentionDays')) {
        $targetInteractive = $InteractiveRetentionDays
        $targetTotal = $TotalRetentionDays
        $source = "Default"
    }
    else {
        $targetInteractive = $null
        $targetTotal = $null
        $source = "N/A"
    }

    $result = [PSCustomObject]@{
        Table                   = $tableName
        Plan                    = $plan
        CurrentInteractiveDays  = $currentInteractive
        CurrentTotalDays        = $currentTotal
        TargetInteractiveDays   = if ($targetInteractive) { $targetInteractive } else { "-" }
        TargetTotalDays         = if ($targetTotal) { $targetTotal } else { "-" }
        Source                  = $source
        Status                  = ""
    }

    if ($ReportOnly) {
        $result.Status = "Report Only"
        $results += $result
        continue
    }

    if ($null -eq $targetInteractive) {
        $result.Status = "Skipped (no target)"
        $results += $result
        continue
    }

    # Skip if already at target
    if ($currentInteractive -eq $targetInteractive -and $currentTotal -eq $targetTotal) {
        $result.Status = "Already at target"
        $results += $result
        continue
    }

    # Confirm before applying
    Write-Host "`n--- $tableName ---" -ForegroundColor Yellow
    Write-Host "  Plan:                $plan"
    Write-Host "  Current Interactive: $currentInteractive days"
    Write-Host "  Current Total:       $currentTotal days"
    Write-Host "  Target Interactive:  $targetInteractive days" -ForegroundColor Green
    Write-Host "  Target Total:        $targetTotal days" -ForegroundColor Green
    Write-Host "  Source:              $source"

    if ($PSCmdlet.ShouldProcess($tableName, "Update retention to Interactive=$targetInteractive, Total=$targetTotal")) {
        $confirm = Read-Host "  Apply changes to '$tableName'? (y/n/a=all remaining/q=quit)"

        if ($confirm -eq 'q') {
            Write-Host "Quitting. No further changes will be made." -ForegroundColor Yellow
            $result.Status = "Quit"
            $results += $result
            break
        }

        if ($confirm -eq 'a') {
            $script:applyAll = $true
        }

        if ($confirm -ne 'y' -and $confirm -ne 'a' -and -not $script:applyAll) {
            $result.Status = "Skipped by user"
            $results += $result
            continue
        }

        # Apply the update
        $body = @{
            properties = @{
                retentionInDays      = $targetInteractive
                totalRetentionInDays = $targetTotal
            }
        } | ConvertTo-Json -Depth 5

        try {
            $updateResponse = Invoke-AzRestMethod -Method PATCH -Path "$basePath/tables/$($tableName)?api-version=$apiVersion" -Payload $body
            if ($updateResponse.StatusCode -in 200, 202) {
                Write-Host "  Updated successfully." -ForegroundColor Green
                $result.Status = "Updated"
            }
            else {
                $errorDetail = ($updateResponse.Content | ConvertFrom-Json -ErrorAction SilentlyContinue).error.message
                if (-not $errorDetail) { $errorDetail = $updateResponse.Content }
                Write-Warning "  Failed to update '$tableName'. Status: $($updateResponse.StatusCode). Error: $errorDetail"
                $result.Status = "Failed: $errorDetail"
            }
        }
        catch {
            Write-Warning "  Error updating '$tableName': $_"
            $result.Status = "Error: $_"
        }
    }

    $results += $result
}

# --- Summary ---
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

# Export summary to CSV
$summaryPath = "retention-update-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv"
$results | Export-Csv -Path $summaryPath -NoTypeInformation
Write-Host "Summary exported to: $summaryPath" -ForegroundColor Cyan
