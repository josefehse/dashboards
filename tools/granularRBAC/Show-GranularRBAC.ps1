<#
.SYNOPSIS
    Shows all granular RBAC assignments on a Log Analytics workspace.

.DESCRIPTION
    Retrieves and displays all role assignments with ABAC conditions on the specified
    Log Analytics workspace. Parses conditions to extract table names, column names,
    and allowed values for easy review.

    Useful for auditing who has granular access to what data.

.PARAMETER WorkspaceResourceId
    Full resource ID of the Log Analytics workspace.
    Example: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.OperationalInsights/workspaces/<name>

.PARAMETER GroupObjectId
    Optional. Filter results to a specific Entra ID group object ID.

.PARAMETER TableName
    Optional. Filter results to assignments that reference a specific table.

.PARAMETER IncludeBroadRoles
    Include assignments without ABAC conditions (broad access roles).

.PARAMETER Detailed
    Show full ABAC condition text in the output.

.EXAMPLE
    .\Show-GranularRBAC.ps1 `
        -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace"

.EXAMPLE
    .\Show-GranularRBAC.ps1 `
        -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
        -TableName "CommonSecurityLog" `
        -Detailed
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$WorkspaceResourceId,

    [Parameter()]
    [string]$GroupObjectId,

    [Parameter()]
    [string]$TableName,

    [Parameter()]
    [switch]$IncludeBroadRoles,

    [Parameter()]
    [switch]$Detailed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

#region --- Prerequisites ---
Write-Host "Checking prerequisites..." -ForegroundColor Cyan

$context = Get-AzContext
if (-not $context) {
    Write-Error "Not logged in to Azure. Run Connect-AzAccount first."
    return
}
Write-Host "Logged in as: $($context.Account.Id)" -ForegroundColor Green
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

#region --- Helper function to parse ABAC condition ---
function ConvertFrom-AbacCondition {
    param([string]$Condition)

    $result = [PSCustomObject]@{
        TableName    = $null
        ColumnName   = $null
        ColumnValues = @()
    }

    if ([string]::IsNullOrWhiteSpace($Condition)) {
        return $result
    }

    # Extract table name: @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals 'TableName'
    if ($Condition -match "tables:name\]\s+StringEquals\s+'([^']+)'") {
        $result.TableName = $Matches[1]
    }

    # Extract column name: @Resource[...tables/record:ColumnName<$key_case_sensitive$>]
    if ($Condition -match "tables/record:([^\<\]]+)") {
        $result.ColumnName = $Matches[1]
    }

    # Extract column values: ForAnyOfAnyValues:StringLikeIgnoreCase {'Value1', 'Value2'}
    if ($Condition -match "StringLikeIgnoreCase\s*\{([^}]+)\}") {
        $valuesString = $Matches[1]
        $result.ColumnValues = $valuesString -split "',\s*'" | ForEach-Object { $_.Trim("'", " ") }
    }

    return $result
}
#endregion

#region --- Get role assignments ---
Write-Host "`nRetrieving role assignments..." -ForegroundColor Cyan

$getParams = @{
    Scope       = $WorkspaceResourceId
    ErrorAction = "SilentlyContinue"
}

if ($GroupObjectId) {
    $getParams.ObjectId = $GroupObjectId
}

$allAssignments = @(Get-AzRoleAssignment @getParams)

if ($allAssignments.Count -eq 0) {
    Write-Host "No role assignments found on this workspace." -ForegroundColor Yellow
    return
}

Write-Host "Found $($allAssignments.Count) total role assignment(s)." -ForegroundColor Green
#endregion

#region --- Process and filter assignments ---
$results = @()
$granularCount = 0
$broadCount = 0

foreach ($assignment in $allAssignments) {
    $hasCondition = -not [string]::IsNullOrWhiteSpace($assignment.Condition)
    $parsedCondition = $null

    if ($hasCondition) {
        $parsedCondition = ConvertFrom-AbacCondition -Condition $assignment.Condition

        # Filter by table name if specified
        if ($TableName -and $parsedCondition.TableName -ne $TableName) {
            continue
        }

        $granularCount++
    } else {
        $broadCount++
        if (-not $IncludeBroadRoles) {
            continue
        }
    }

    # Resolve principal display name
    $principalName = $assignment.DisplayName
    if (-not $principalName) {
        $principalName = $assignment.ObjectId
    }

    $resultObj = [PSCustomObject]@{
        PrincipalName    = $principalName
        PrincipalId      = $assignment.ObjectId
        PrincipalType    = $assignment.ObjectType
        RoleDefinition   = $assignment.RoleDefinitionName
        HasCondition     = $hasCondition
        TableName        = if ($parsedCondition) { $parsedCondition.TableName } else { "N/A (Broad Access)" }
        ColumnName       = if ($parsedCondition) { $parsedCondition.ColumnName } else { "N/A" }
        ColumnValues     = if ($parsedCondition -and @($parsedCondition.ColumnValues).Count -gt 0) {
                               $parsedCondition.ColumnValues -join ", "
                           } else { "N/A" }
        AssignmentId     = $assignment.RoleAssignmentId
        Condition        = $assignment.Condition
    }

    $results += $resultObj
}
#endregion

#region --- Display results ---
Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host "GRANULAR RBAC SUMMARY" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Workspace      : $($workspace.Name)"
Write-Host "Resource Group : $(($WorkspaceResourceId -split '/')[4])"
Write-Host "Subscription   : $(($WorkspaceResourceId -split '/')[2])"
Write-Host ""
Write-Host "Granular RBAC assignments (with ABAC conditions) : $granularCount" -ForegroundColor Green
Write-Host "Broad access assignments (without conditions)    : $broadCount" -ForegroundColor $(if ($broadCount -gt 0) { "Yellow" } else { "Green" })

if ($TableName) {
    Write-Host "Filtered by table: $TableName" -ForegroundColor Magenta
}
if ($GroupObjectId) {
    Write-Host "Filtered by group: $GroupObjectId" -ForegroundColor Magenta
}
Write-Host ""

if (@($results).Count -eq 0) {
    Write-Host "No matching assignments found." -ForegroundColor Yellow
    return
}

# Display granular assignments
$granularResults = @($results | Where-Object { $_.HasCondition -eq $true })
if ($granularResults.Count -gt 0) {
    Write-Host "--- Granular RBAC Assignments ---" -ForegroundColor Yellow
    Write-Host ""

    foreach ($r in $granularResults) {
        Write-Host "Principal     : $($r.PrincipalName)" -ForegroundColor White
        Write-Host "  Object ID   : $($r.PrincipalId)" -ForegroundColor DarkGray
        Write-Host "  Type        : $($r.PrincipalType)" -ForegroundColor DarkGray
        Write-Host "  Role        : $($r.RoleDefinition)" -ForegroundColor Cyan
        Write-Host "  Table       : $($r.TableName)" -ForegroundColor Green
        Write-Host "  Column      : $($r.ColumnName)" -ForegroundColor Green
        Write-Host "  Values      : $($r.ColumnValues)" -ForegroundColor Green

        if ($Detailed -and $r.Condition) {
            Write-Host "  Condition   :" -ForegroundColor DarkYellow
            Write-Host ($r.Condition -split "`n" | ForEach-Object { "    $_" }) -ForegroundColor DarkGray
        }
        Write-Host ""
    }
}

# Display broad assignments if included
$broadResults = @($results | Where-Object { $_.HasCondition -eq $false })
if ($broadResults.Count -gt 0) {
    Write-Host "--- Broad Access Assignments (No ABAC Condition) ---" -ForegroundColor Yellow
    Write-Host ""

    foreach ($r in $broadResults) {
        Write-Host "Principal     : $($r.PrincipalName)" -ForegroundColor White
        Write-Host "  Object ID   : $($r.PrincipalId)" -ForegroundColor DarkGray
        Write-Host "  Type        : $($r.PrincipalType)" -ForegroundColor DarkGray
        Write-Host "  Role        : $($r.RoleDefinition)" -ForegroundColor Red
        Write-Host ""
    }

    Write-Host "⚠️  Warning: Broad access roles may override granular RBAC restrictions!" -ForegroundColor Yellow
    Write-Host ""
}
#endregion

#region --- Export option ---
Write-Host "--- Export ---" -ForegroundColor Cyan
Write-Host "To export results to CSV, pipe to Export-Csv:" -ForegroundColor DarkGray
Write-Host '  .\Show-GranularRBAC.ps1 -WorkspaceResourceId "..." | Export-Csv -Path "rbac-report.csv" -NoTypeInformation' -ForegroundColor DarkGray
Write-Host ""

# Return results for pipeline usage
$results | Select-Object PrincipalName, PrincipalId, PrincipalType, RoleDefinition, TableName, ColumnName, ColumnValues
#endregion
