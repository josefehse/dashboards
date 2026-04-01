<#
.SYNOPSIS
    Onboards one or more Entra ID groups with granular RBAC access to a Log Analytics table,
    filtered by a column with specific value(s).

.DESCRIPTION
    Creates Azure role assignments with ABAC conditions that restrict data access to rows
    in a specific Log Analytics table where a column matches the provided value(s).
    Uses the "No access to data, except what is allowed" (restrictive) strategy.

    Requires Az.Resources and Az.OperationalInsights modules.

.PARAMETER WorkspaceResourceId
    Full resource ID of the Log Analytics workspace.
    Example: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.OperationalInsights/workspaces/<name>

.PARAMETER GroupNames
    One or more Entra ID group display names to grant access.
    Each name must resolve to exactly one group (duplicates will cause an error).

.PARAMETER TableName
    The Log Analytics table to grant access to (e.g., CommonSecurityLog).

.PARAMETER ColumnName
    The column name to filter on (e.g., DeviceVendor).

.PARAMETER ColumnValues
    One or more allowed values for the column filter.

.PARAMETER RoleDefinitionName
    Role to assign. Defaults to 'Log Analytics Data Reader'.

.PARAMETER WhatIf
    Preview the role assignments without creating them.

.EXAMPLE
    .\Grant-GranularRBAC.ps1 `
        -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
        -GroupNames "FirewallAdmins", "NetworkOps" `
        -TableName "CommonSecurityLog" `
        -ColumnName "DeviceVendor" `
        -ColumnValues "Check Point", "SonicWall"
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$WorkspaceResourceId,

    [Parameter(Mandatory)]
    [string[]]$GroupNames,

    [Parameter(Mandatory)]
    [string]$TableName,

    [Parameter(Mandatory)]
    [string]$ColumnName,

    [Parameter(Mandatory)]
    [string[]]$ColumnValues,

    [Parameter()]
    [string]$RoleDefinitionName = "Log Analytics Data Reader"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

#region --- Prerequisites ---
Write-Host "Checking prerequisites..." -ForegroundColor Cyan

$requiredModules = @("Az.Resources", "Az.OperationalInsights")
foreach ($mod in $requiredModules) {
    if (-not (Get-Module -ListAvailable -Name $mod)) {
        Write-Error "Required module '$mod' is not installed. Run: Install-Module $mod -Scope CurrentUser"
        return
    }
}

$context = Get-AzContext
if (-not $context) {
    Write-Error "Not logged in to Azure. Run Connect-AzAccount first."
    return
}
Write-Host "Logged in as: $($context.Account.Id)" -ForegroundColor Green
#endregion

#region --- Resolve group names to object IDs ---
Write-Host "Resolving group names..." -ForegroundColor Cyan

$resolvedGroups = @()
foreach ($groupName in $GroupNames) {
    $groups = @(Get-AzADGroup -DisplayName $groupName -ErrorAction SilentlyContinue)
    
    if ($groups.Count -eq 0) {
        Write-Error "Group '$groupName' not found in Entra ID."
        return
    }
    if ($groups.Count -gt 1) {
        Write-Error "Multiple groups found with name '$groupName' (found $($groups.Count)). Use unique group names or specify Object IDs directly."
        Write-Host "  Matching groups:" -ForegroundColor Yellow
        $groups | ForEach-Object { Write-Host "    - $($_.DisplayName) (ID: $($_.Id))" -ForegroundColor Yellow }
        return
    }
    
    $resolvedGroups += [PSCustomObject]@{
        Name     = $groupName
        ObjectId = $groups[0].Id
    }
    Write-Host "  $groupName -> $($groups[0].Id)" -ForegroundColor Green
}
#endregion

#region --- Validate workspace ---
Write-Host "Validating workspace..." -ForegroundColor Cyan
try {
    $workspace = Get-AzResource -ResourceId $WorkspaceResourceId -ErrorAction Stop
    Write-Host "Workspace found: $($workspace.Name)" -ForegroundColor Green
} catch {
    Write-Error "Workspace not found or not accessible: $WorkspaceResourceId"
    return
}
#endregion

#region --- Check for conflicting role assignments ---
Write-Host "Checking for conflicting role assignments..." -ForegroundColor Cyan

$broadRoles = @("Log Analytics Reader", "Reader", "Contributor", "Owner")
$parentScope = ($WorkspaceResourceId -split "/providers/Microsoft.OperationalInsights")[0]

foreach ($group in $resolvedGroups) {
    $existing = Get-AzRoleAssignment -ObjectId $group.ObjectId -Scope $WorkspaceResourceId -ErrorAction SilentlyContinue
    $parentAssignments = Get-AzRoleAssignment -ObjectId $group.ObjectId -Scope $parentScope -ErrorAction SilentlyContinue

    $allAssignments = @($existing) + @($parentAssignments) | Where-Object { $_ -ne $null }

    foreach ($assignment in $allAssignments) {
        if ($assignment.RoleDefinitionName -in $broadRoles -and [string]::IsNullOrEmpty($assignment.Condition)) {
            Write-Warning ("Group '$($group.Name)' has broad role '$($assignment.RoleDefinitionName)' at scope " +
                "'$($assignment.Scope)' without conditions. This may override the granular RBAC restriction.")
        }
    }
}
#endregion

#region --- Build ABAC condition ---
$valuesFormatted = ($ColumnValues | ForEach-Object { "'$_'" }) -join ", "

$condition = @"
(
 (
  !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})
 )
 OR
 (
  @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals '$TableName'
  AND
  @Resource[Microsoft.OperationalInsights/workspaces/tables/record:$ColumnName<`$key_case_sensitive`$>] ForAnyOfAnyValues:StringLikeIgnoreCase {$valuesFormatted}
 )
)
"@

$conditionVersion = "2.0"

Write-Host "`nABAC Condition:" -ForegroundColor Yellow
Write-Host $condition
#endregion

#region --- Resolve role definition ---
$roleDef = Get-AzRoleDefinition -Name $RoleDefinitionName
if (-not $roleDef) {
    Write-Error "Role definition '$RoleDefinitionName' not found."
    return
}
Write-Host "`nUsing role: $($roleDef.Name) ($($roleDef.Id))" -ForegroundColor Green
#endregion

#region --- Create role assignments ---
$results = @()

foreach ($group in $resolvedGroups) {
    Write-Host "`nProcessing group: $($group.Name) ($($group.ObjectId))" -ForegroundColor Cyan

    if ($PSCmdlet.ShouldProcess("Group $($group.Name)", "Assign '$RoleDefinitionName' with ABAC condition on $TableName")) {
        try {
            $assignment = New-AzRoleAssignment `
                -ObjectId $group.ObjectId `
                -RoleDefinitionId $roleDef.Id `
                -Scope $WorkspaceResourceId `
                -Condition $condition `
                -ConditionVersion $conditionVersion

            Write-Host "  Role assignment created: $($assignment.RoleAssignmentId)" -ForegroundColor Green
            $results += [PSCustomObject]@{
                GroupName        = $group.Name
                GroupObjectId    = $group.ObjectId
                RoleAssignmentId = $assignment.RoleAssignmentId
                Status           = "Created"
            }
        } catch {
            if ($_.Exception.Message -like "*Conflict*" -or $_.Exception.Message -like "*already exists*") {
                Write-Warning "  Role assignment already exists for group $($group.Name). Skipping."
                $results += [PSCustomObject]@{
                    GroupName        = $group.Name
                    GroupObjectId    = $group.ObjectId
                    RoleAssignmentId = "N/A"
                    Status           = "AlreadyExists"
                }
            } else {
                Write-Error "  Failed to create role assignment for group $($group.Name): $_"
                $results += [PSCustomObject]@{
                    GroupName        = $group.Name
                    GroupObjectId    = $group.ObjectId
                    RoleAssignmentId = "N/A"
                    Status           = "Failed: $_"
                }
            }
        }
    }
}
#endregion

#region --- Summary ---
Write-Host "`n--- Summary ---" -ForegroundColor Yellow
Write-Host "Workspace : $($workspace.Name)"
Write-Host "Table     : $TableName"
Write-Host "Column    : $ColumnName"
Write-Host "Values    : $($ColumnValues -join ', ')"
Write-Host "Role      : $RoleDefinitionName"
Write-Host ""
$results | Format-Table -AutoSize

if ($results.Status -contains "Created") {
    Write-Host "Note: Changes may take up to 15 minutes to take effect." -ForegroundColor Yellow
}
#endregion
