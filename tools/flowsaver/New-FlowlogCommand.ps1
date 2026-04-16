<#
.SYNOPSIS
    Browse Azure storage accounts and generate flowlog CLI commands with a fresh SAS token.

.DESCRIPTION
    Interactive script that:
    1. Lists storage accounts in the current subscription (or all subscriptions)
    2. Lets you select one via console menu
    3. Generates a 60-minute SAS token with read/list permissions
    4. Outputs ready-to-use flowlog commands for both Bash and PowerShell

.PARAMETER Subscription
    Azure subscription name or ID. If omitted, uses current context or lists all.

.PARAMETER LastHours
    Generate command for --last-hours N (default: 4)

.PARAMETER LastDays
    Generate command for --last N days instead of hours

.PARAMETER Container
    Blob container name (default: insights-logs-flowlogflowevent)

.PARAMETER AllSubscriptions
    Search across all accessible subscriptions

.EXAMPLE
    .\New-FlowlogCommand.ps1
    # Interactive selection, generates command for last 4 hours

.EXAMPLE
    .\New-FlowlogCommand.ps1 -LastHours 12
    # Generate command for last 12 hours

.EXAMPLE
    .\New-FlowlogCommand.ps1 -LastDays 2 -AllSubscriptions
    # Search all subscriptions, generate command for last 2 days
#>

[CmdletBinding()]
param(
    [string]$Subscription,
    [int]$LastHours = 4,
    [int]$LastDays,
    [string]$Container = "insights-logs-flowlogflowevent",
    [switch]$AllSubscriptions
)

#Requires -Modules Az.Accounts, Az.Storage

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Menu {
    param(
        [Parameter(Mandatory)]
        [array]$Items,
        [Parameter(Mandatory)]
        [string]$Prompt,
        [Parameter(Mandatory)]
        [scriptblock]$DisplayProperty
    )

    if ($Items.Count -eq 0) {
        Write-Host "No items found." -ForegroundColor Yellow
        return $null
    }

    Write-Host ""
    Write-Host $Prompt -ForegroundColor Cyan
    Write-Host ("-" * 60)

    for ($i = 0; $i -lt $Items.Count; $i++) {
        $display = & $DisplayProperty $Items[$i]
        Write-Host ("  [{0,2}] {1}" -f ($i + 1), $display)
    }

    Write-Host ""
    do {
        $selection = Read-Host "Enter number (1-$($Items.Count)) or 'q' to quit"
        if ($selection -eq 'q') { return $null }
        $index = 0
        $valid = [int]::TryParse($selection, [ref]$index) -and $index -ge 1 -and $index -le $Items.Count
        if (-not $valid) {
            Write-Host "Invalid selection. Try again." -ForegroundColor Yellow
        }
    } while (-not $valid)

    return $Items[$index - 1]
}

# Ensure logged in
$context = Get-AzContext -ErrorAction SilentlyContinue
if (-not $context) {
    Write-Host "Not logged in to Azure. Running Connect-AzAccount..." -ForegroundColor Yellow
    Connect-AzAccount
    $context = Get-AzContext
}

Write-Host "Current context: $($context.Account.Id) @ $($context.Subscription.Name)" -ForegroundColor Gray

# Get storage accounts
$storageAccounts = @()

if ($AllSubscriptions) {
    Write-Host "Searching all subscriptions..." -ForegroundColor Cyan
    $subs = Get-AzSubscription | Where-Object { $_.State -eq 'Enabled' }
    foreach ($sub in $subs) {
        Write-Host "  Checking $($sub.Name)..." -ForegroundColor Gray -NoNewline
        $null = Set-AzContext -SubscriptionId $sub.Id -WarningAction SilentlyContinue
        $accounts = Get-AzStorageAccount -ErrorAction SilentlyContinue
        $count = ($accounts | Measure-Object).Count
        Write-Host " ($count accounts)"
        foreach ($sa in $accounts) {
            $storageAccounts += [PSCustomObject]@{
                Name           = $sa.StorageAccountName
                ResourceGroup  = $sa.ResourceGroupName
                Location       = $sa.Location
                Subscription   = $sub.Name
                SubscriptionId = $sub.Id
            }
        }
    }
    # Restore original context
    $null = Set-AzContext -SubscriptionId $context.Subscription.Id -WarningAction SilentlyContinue
}
elseif ($Subscription) {
    $null = Set-AzContext -Subscription $Subscription
    $context = Get-AzContext
    Write-Host "Listing storage accounts in $($context.Subscription.Name)..." -ForegroundColor Cyan
    $accounts = Get-AzStorageAccount
    foreach ($sa in $accounts) {
        $storageAccounts += [PSCustomObject]@{
            Name           = $sa.StorageAccountName
            ResourceGroup  = $sa.ResourceGroupName
            Location       = $sa.Location
            Subscription   = $context.Subscription.Name
            SubscriptionId = $context.Subscription.Id
        }
    }
}
else {
    Write-Host "Listing storage accounts in $($context.Subscription.Name)..." -ForegroundColor Cyan
    $accounts = Get-AzStorageAccount
    foreach ($sa in $accounts) {
        $storageAccounts += [PSCustomObject]@{
            Name           = $sa.StorageAccountName
            ResourceGroup  = $sa.ResourceGroupName
            Location       = $sa.Location
            Subscription   = $context.Subscription.Name
            SubscriptionId = $context.Subscription.Id
        }
    }
}

if ($storageAccounts.Count -eq 0) {
    Write-Error "No storage accounts found."
}

# Select storage account
$selected = Show-Menu -Items $storageAccounts -Prompt "Select a storage account:" -DisplayProperty {
    param($item)
    if ($AllSubscriptions) {
        "$($item.Name) ($($item.Location)) [$($item.Subscription)]"
    }
    else {
        "$($item.Name) ($($item.Location), $($item.ResourceGroup))"
    }
}

if (-not $selected) {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Selected: $($selected.Name)" -ForegroundColor Green

# Switch to correct subscription if needed
if ($selected.SubscriptionId -ne (Get-AzContext).Subscription.Id) {
    Write-Host "Switching to subscription: $($selected.Subscription)" -ForegroundColor Gray
    $null = Set-AzContext -SubscriptionId $selected.SubscriptionId -WarningAction SilentlyContinue
}

# Generate SAS token (60 minutes)
Write-Host "Generating SAS token (valid for 60 minutes)..." -ForegroundColor Cyan

$storageAccount = Get-AzStorageAccount -ResourceGroupName $selected.ResourceGroup -Name $selected.Name
$ctx = $storageAccount.Context

$sasParams = @{
    Context    = $ctx
    Service    = "Blob"
    ResourceType = "Container", "Object"
    Permission = "rl"  # read + list
    ExpiryTime = (Get-Date).AddMinutes(60)
}

$sasToken = New-AzStorageAccountSASToken @sasParams
# Remove leading '?' if present
$sasToken = $sasToken.TrimStart('?')

# Build time range parameter
if ($LastDays) {
    $timeParam = "--last $LastDays"
    $timeDesc = "last $LastDays day(s)"
}
else {
    $timeParam = "--last-hours $LastHours"
    $timeDesc = "last $LastHours hour(s)"
}

# Output commands
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "FLOWLOG COMMANDS - $timeDesc" -ForegroundColor Cyan
Write-Host "Storage Account: $($selected.Name)" -ForegroundColor Gray
Write-Host "Container: $Container" -ForegroundColor Gray
Write-Host "SAS Token Expires: $((Get-Date).AddMinutes(60).ToString('yyyy-MM-dd HH:mm:ss')) UTC" -ForegroundColor Gray
Write-Host ("=" * 70) -ForegroundColor DarkGray

Write-Host ""
Write-Host "### Bash ###" -ForegroundColor Yellow
Write-Host @"
flowlog generate-kql \
  --storage-account $($selected.Name) \
  --container $Container \
  $timeParam \
  --sas-token "$sasToken"
"@

Write-Host ""
Write-Host "### PowerShell ###" -ForegroundColor Yellow
Write-Host @"
flowlog generate-kql ``
  --storage-account $($selected.Name) ``
  --container $Container ``
  $timeParam ``
  --sas-token "$sasToken"
"@

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkGray

# Copy to clipboard if available
try {
    $pwshCmd = @"
flowlog generate-kql ``
  --storage-account $($selected.Name) ``
  --container $Container ``
  $timeParam ``
  --sas-token "$sasToken"
"@
    $pwshCmd | Set-Clipboard
    Write-Host "PowerShell command copied to clipboard!" -ForegroundColor Green
}
catch {
    Write-Host "(Clipboard not available)" -ForegroundColor Gray
}
