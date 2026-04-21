# Azure Update Manager - API Scripts

Command-line scripts for assessing and triggering patching via the Azure Update Manager REST API. Supports both **Azure VMs** and **Arc-enabled hybrid machines**.

## Scripts

| Script | Description |
|--------|-------------|
| `Invoke-AUMAssessPatches.ps1` | Trigger patch assessment on one or more machines |
| `Invoke-AUMInstallPatches.ps1` | Install patches on one or more machines |
| `AUM-ApiCommon.psm1` | Shared module (auth, REST calls, async polling) |

## Prerequisites

- **PowerShell 7+**
- **Azure CLI** installed and authenticated (`az login`) — for current-user auth
- Or an **Azure AD App Registration** with client secret — for service principal auth

### Required RBAC

The authenticated identity needs these roles on the target machines:

| Role | Scope | Purpose |
|------|-------|---------|
| Virtual Machine Contributor | VM / Resource Group | Trigger assess & install on Azure VMs |
| Azure Connected Machine Resource Administrator | Machine / Resource Group | Trigger assess & install on Arc machines |

## Authentication

### Option 1: Current User (az CLI) — Default

```powershell
# Login once
az login

# Scripts automatically use your current session
.\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM"
```

### Option 2: Service Principal

```powershell
.\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM" `
    -ClientId "app-id" -ClientSecret "secret" -TenantId "tenant-id"
```

## Usage Examples

### Assess Patches

```powershell
# Single Azure VM (uses current az CLI subscription)
.\Invoke-AUMAssessPatches.ps1 -ResourceGroup "myRG" -MachineName "myVM"

# Explicit subscription
.\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM"

# Arc-enabled hybrid machine
.\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "onpremServer" -MachineType Arc

# Multiple machines
.\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "vm1","vm2","vm3"

# Using full resource ID (auto-detects machine type)
.\Invoke-AUMAssessPatches.ps1 -ResourceId "/subscriptions/xxxx/resourceGroups/myRG/providers/Microsoft.HybridCompute/machines/myArcServer"

# Fire-and-forget (don't wait for results)
.\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM" -NoWait
```

### Install Patches

```powershell
# Windows Azure VM — critical & security patches
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM" `
    -OSType Windows -Classifications Critical,Security

# Arc-enabled hybrid machine
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "onpremServer" `
    -MachineType Arc -OSType Windows -Classifications Security

# Linux VM — all security patches, no reboot
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "linuxVM" `
    -OSType Linux -Classifications Security -RebootSetting NeverReboot

# Windows with specific KBs excluded
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM" `
    -OSType Windows -Classifications Critical,Security -KBsToExclude "KB5001234","KB5005678"

# Linux with specific packages
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "linuxVM" `
    -OSType Linux -Classifications Security -PackagesToInclude "openssl","kernel*"

# Dry run (WhatIf)
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM" `
    -OSType Windows -Classifications Critical -WhatIf

# Custom duration and wait time
.\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "myVM" `
    -OSType Windows -Classifications Security -MaximumDuration PT4H -MaxWaitSeconds 7200
```

### Working with Results

Both scripts return structured objects you can capture and inspect:

```powershell
# Capture results
$results = .\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxxx" -ResourceGroup "myRG" -MachineName "vm1","vm2"

# Check status
$results | Format-Table MachineName, MachineType, Status

# Drill into full API response
$results[0].Result | ConvertTo-Json -Depth 10
```

## Parameters Reference

### Common Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `-SubscriptionId` | String | Azure subscription ID (defaults to current az CLI subscription) |
| `-ResourceGroup` | String | Resource group name |
| `-MachineName` | String[] | Machine name(s), accepts pipeline |
| `-MachineType` | String | `AzureVM` (default) or `Arc` |
| `-ResourceId` | String[] | Full resource ID(s), auto-detects machine type |
| `-ClientId` | String | Service principal app ID |
| `-ClientSecret` | String | Service principal secret |
| `-TenantId` | String | Azure AD tenant ID |
| `-NoWait` | Switch | Don't wait for operation to complete |
| `-MaxWaitSeconds` | Int | Max poll time (default: 600 for assess, 3600 for install) |

### Install-Specific Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `-OSType` | String | `Windows` or `Linux` (required) |
| `-Classifications` | String[] | Update classifications (required) |
| `-MaximumDuration` | String | ISO 8601 duration (default: `PT2H`) |
| `-RebootSetting` | String | `IfRequired`, `NeverReboot`, `AlwaysReboot` |
| `-KBsToInclude` | String[] | Windows KB IDs to include |
| `-KBsToExclude` | String[] | Windows KB IDs to exclude |
| `-PackagesToInclude` | String[] | Linux package masks to include |
| `-PackagesToExclude` | String[] | Linux package masks to exclude |
| `-MaxPatchPublishDate` | String | Only patches published on/before this date |
| `-WhatIf` | Switch | Preview the action without executing |

## API Reference

Based on the [Azure Update Manager REST API](https://learn.microsoft.com/en-us/azure/update-manager/manage-vms-programmatically).
