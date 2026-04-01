<#
.SYNOPSIS
    Removes granular RBAC role assignments from one or more Entra ID groups
    on a Log Analytics workspace.

.DESCRIPTION
    Finds and removes role assignments with ABAC conditions that match the specified
    table name for the given groups. Useful for offboarding teams from granular access.

.PARAMETER WorkspaceResourceId
    Full resource ID of the Log Analytics workspace.

.PARAMETER GroupObjectIds
    One or more Entra ID group object IDs to revoke access from.

.PARAMETER TableName
    The Log Analytics table name to match in the ABAC condition.
    Only assignments whose condition references this table will be removed.

.PARAMETER RoleDefinitionName
    Role to look for. Defaults to 'Log Analytics Data Reader'.

.PARAMETER Force
    Skip confirmation prompts.

.EXAMPLE
    .\Revoke-GranularRBAC.ps1 `
        -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
        -GroupObjectIds "aaaa-bbbb-cccc" `
        -TableName "CommonSecurityLog"
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$WorkspaceResourceId,

    [Parameter(Mandatory)]
    [string[]]$GroupObjectIds,

    [Parameter(Mandatory)]
    [string]$TableName,

    [Parameter()]
    [string]$RoleDefinitionName = "Log Analytics Data Reader",

    [Parameter()]
    [switch]$Force
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

#region --- Find and remove assignments ---
$results = @()

foreach ($groupId in $GroupObjectIds) {
    Write-Host "`nProcessing group: $groupId" -ForegroundColor Cyan

    $assignments = Get-AzRoleAssignment `
        -ObjectId $groupId `
        -Scope $WorkspaceResourceId `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.RoleDefinitionName -eq $RoleDefinitionName -and
            $_.Condition -and
            $_.Condition -like "*$TableName*"
        }

    if (-not $assignments -or $assignments.Count -eq 0) {
        Write-Host "  No matching granular RBAC assignments found." -ForegroundColor Yellow
        $results += [PSCustomObject]@{
            GroupObjectId    = $groupId
            RoleAssignmentId = "N/A"
            Status           = "NotFound"
        }
        continue
    }

    foreach ($assignment in $assignments) {
        Write-Host "  Found assignment: $($assignment.RoleAssignmentId)" -ForegroundColor White
        Write-Host "  Condition snippet: $($assignment.Condition.Substring(0, [Math]::Min(120, $assignment.Condition.Length)))..." -ForegroundColor DarkGray

        $shouldRemove = $Force
        if (-not $Force) {
            if ($PSCmdlet.ShouldProcess(
                "Assignment $($assignment.RoleAssignmentId) for group $groupId",
                "Remove granular RBAC role assignment")) {
                $shouldRemove = $true
            }
        }

        if ($shouldRemove) {
            try {
                Remove-AzRoleAssignment `
                    -InputObject $assignment `
                    -ErrorAction Stop

                Write-Host "  Removed successfully." -ForegroundColor Green
                $results += [PSCustomObject]@{
                    GroupObjectId    = $groupId
                    RoleAssignmentId = $assignment.RoleAssignmentId
                    Status           = "Removed"
                }
            } catch {
                Write-Error "  Failed to remove assignment: $_"
                $results += [PSCustomObject]@{
                    GroupObjectId    = $groupId
                    RoleAssignmentId = $assignment.RoleAssignmentId
                    Status           = "Failed: $_"
                }
            }
        } else {
            $results += [PSCustomObject]@{
                GroupObjectId    = $groupId
                RoleAssignmentId = $assignment.RoleAssignmentId
                Status           = "Skipped"
            }
        }
    }
}
#endregion

#region --- Summary ---
Write-Host "`n--- Revocation Summary ---" -ForegroundColor Yellow
Write-Host "Workspace : $(($WorkspaceResourceId -split '/')[-1])"
Write-Host "Table     : $TableName"
Write-Host "Role      : $RoleDefinitionName"
Write-Host ""
$results | Format-Table -AutoSize

if ($results.Status -contains "Removed") {
    Write-Host "Note: Changes may take up to 15 minutes to take effect." -ForegroundColor Yellow
}
#endregion
