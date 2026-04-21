<#
.SYNOPSIS
    Triggers an Azure Update Manager patch assessment on one or more machines.
.DESCRIPTION
    Calls the AUM assessPatches REST API to evaluate available updates on Azure VMs
    and Arc-enabled hybrid machines. Supports authentication via az CLI (current user)
    or service principal credentials.
.PARAMETER SubscriptionId
    Azure subscription ID. If omitted, uses the current az CLI subscription.
.PARAMETER ResourceGroup
    Resource group containing the target machines.
.PARAMETER MachineName
    One or more machine names to assess. Accepts pipeline input.
.PARAMETER MachineType
    Machine type: AzureVM (default) or Arc (for hybrid/on-prem machines).
.PARAMETER ResourceId
    One or more full resource IDs. Supports both Microsoft.Compute/virtualMachines
    and Microsoft.HybridCompute/machines. Alternative to SubscriptionId/ResourceGroup/MachineName.
.PARAMETER ClientId
    Application (client) ID for service principal authentication.
.PARAMETER ClientSecret
    Client secret for service principal authentication.
.PARAMETER TenantId
    Azure AD tenant ID for service principal authentication.
.PARAMETER NoWait
    Return immediately after triggering the assessment without waiting for results.
.PARAMETER MaxWaitSeconds
    Maximum seconds to wait for assessment completion. Default: 600.
.EXAMPLE
    # Assess an Azure VM using az CLI auth
    .\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxx" -ResourceGroup "myRG" -MachineName "myVM"
.EXAMPLE
    # Assess an Arc-enabled hybrid machine
    .\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxx" -ResourceGroup "myRG" -MachineName "onpremServer" -MachineType Arc
.EXAMPLE
    # Assess using a resource ID (auto-detects machine type)
    .\Invoke-AUMAssessPatches.ps1 -ResourceId "/subscriptions/xxx/resourceGroups/myRG/providers/Microsoft.HybridCompute/machines/myArcServer"
.EXAMPLE
    # Assess using service principal auth
    .\Invoke-AUMAssessPatches.ps1 -SubscriptionId "xxx" -ResourceGroup "myRG" -MachineName "myVM" `
        -ClientId $appId -ClientSecret $secret -TenantId $tid
#>
[CmdletBinding(DefaultParameterSetName = 'ByName_AzCli')]
param(
    [Parameter(ParameterSetName = 'ByName_AzCli')]
    [Parameter(ParameterSetName = 'ByName_SP')]
    [string]$SubscriptionId,

    [Parameter(ParameterSetName = 'ByName_AzCli', Mandatory)]
    [Parameter(ParameterSetName = 'ByName_SP', Mandatory)]
    [string]$ResourceGroup,

    [Parameter(ParameterSetName = 'ByName_AzCli', Mandatory, ValueFromPipeline)]
    [Parameter(ParameterSetName = 'ByName_SP', Mandatory, ValueFromPipeline)]
    [string[]]$MachineName,

    [Parameter(ParameterSetName = 'ByName_AzCli')]
    [Parameter(ParameterSetName = 'ByName_SP')]
    [ValidateSet('AzureVM', 'Arc')]
    [string]$MachineType = 'AzureVM',

    [Parameter(ParameterSetName = 'ById_AzCli', Mandatory, ValueFromPipeline)]
    [Parameter(ParameterSetName = 'ById_SP', Mandatory, ValueFromPipeline)]
    [string[]]$ResourceId,

    [Parameter(ParameterSetName = 'ByName_SP', Mandatory)]
    [Parameter(ParameterSetName = 'ById_SP', Mandatory)]
    [string]$ClientId,

    [Parameter(ParameterSetName = 'ByName_SP', Mandatory)]
    [Parameter(ParameterSetName = 'ById_SP', Mandatory)]
    [string]$ClientSecret,

    [Parameter(ParameterSetName = 'ByName_SP', Mandatory)]
    [Parameter(ParameterSetName = 'ById_SP', Mandatory)]
    [string]$TenantId,

    [switch]$NoWait,

    [int]$MaxWaitSeconds = 600
)

begin {
    $ErrorActionPreference = 'Stop'
    Import-Module "$PSScriptRoot\AUM-ApiCommon.psm1" -Force

    # Acquire token once
    $tokenParams = @{}
    if ($PSCmdlet.ParameterSetName -match '_SP$') {
        $tokenParams = @{ ClientId = $ClientId; ClientSecret = $ClientSecret; TenantId = $TenantId }
    }
    $token = Get-AUMToken @tokenParams

    # Resolve subscription if not provided
    if ($PSCmdlet.ParameterSetName -match '^ByName' -and -not $SubscriptionId) {
        $SubscriptionId = Get-AUMCurrentSubscription
        Write-Host "Using current subscription: $SubscriptionId"
    }

    $machineResourceIds = [System.Collections.Generic.List[string]]::new()
}

process {
    if ($PSCmdlet.ParameterSetName -match '^ByName') {
        foreach ($name in $MachineName) {
            $machineResourceIds.Add((ConvertTo-MachineResourceId -SubscriptionId $SubscriptionId -ResourceGroup $ResourceGroup -MachineName $name -MachineType $MachineType))
        }
    }
    else {
        foreach ($rid in $ResourceId) {
            $machineResourceIds.Add((ConvertTo-MachineResourceId -ResourceId $rid))
        }
    }
}

end {
    $results = @()

    foreach ($machineRid in $machineResourceIds) {
        $parsed = Split-MachineResourceId -ResourceId $machineRid
        $apiVersion = Get-AUMApiVersion -MachineType $parsed.MachineType
        $typeLabel = if ($parsed.MachineType -eq 'Arc') { 'Arc' } else { 'VM' }

        Write-Host "Assessing patches on $typeLabel`: $($parsed.MachineName) [$($parsed.ResourceGroup)]"

        # Pre-flight: check if machine is running
        $machineState = Get-MachineRunningState -ResourceId $machineRid -MachineType $parsed.MachineType -Token $token
        if (-not $machineState.IsRunning) {
            Write-Warning "  Skipping $($parsed.MachineName): machine is not running (state: $($machineState.State))."
            $results += [PSCustomObject]@{
                MachineName  = $parsed.MachineName
                MachineType  = $parsed.MachineType
                ResourceId   = $machineRid
                Status       = 'Skipped'
                OperationUrl = $null
                Result       = "Machine not running: $($machineState.State)"
            }
            continue
        }

        $uri = "https://management.azure.com$machineRid/assessPatches?api-version=$apiVersion"
        Write-Verbose "POST $uri"

        try {
            $response = Invoke-AUMRestMethod -Method POST -Uri $uri -Token $token

            if ($NoWait) {
                $operationUrl = $null
                if ($response.Headers['Azure-AsyncOperation']) {
                    $operationUrl = ($response.Headers['Azure-AsyncOperation'] | Select-Object -First 1)
                }
                elseif ($response.Headers['Location']) {
                    $operationUrl = ($response.Headers['Location'] | Select-Object -First 1)
                }

                $results += [PSCustomObject]@{
                    MachineName  = $parsed.MachineName
                    MachineType  = $parsed.MachineType
                    ResourceId   = $machineRid
                    Status       = 'Accepted'
                    OperationUrl = $operationUrl
                    Result       = $null
                }
                Write-Host "  Assessment triggered (not waiting). Operation URL saved."
                continue
            }

            $opResult = Wait-AUMAsyncOperation -Response $response -Token $token -MaxWaitSeconds $MaxWaitSeconds

            $status = $opResult.status ?? $opResult.properties.status ?? 'Unknown'
            $results += [PSCustomObject]@{
                MachineName  = $parsed.MachineName
                MachineType  = $parsed.MachineType
                ResourceId   = $machineRid
                Status       = $status
                OperationUrl = $null
                Result       = $opResult
            }

            if ($status -eq 'Succeeded') {
                $patchCount = $opResult.properties.availablePatchCount ?? $opResult.availablePatchCount ?? 'N/A'
                Write-Host "  Assessment complete: $patchCount patches available."
            }
            else {
                Write-Host "  Assessment finished with status: $status"
            }
        }
        catch {
            $errMsg = $_.Exception.Message
            $errDetail = $null
            if ($_.ResponseBody) { $errDetail = $_.ResponseBody }
            elseif ($_.ErrorRecord.ResponseBody) { $errDetail = $_.ErrorRecord.ResponseBody }
            Write-Warning "Failed to assess patches on $($parsed.MachineName): $errMsg"
            if ($errDetail) {
                Write-Warning "  API error detail: $($errDetail | ConvertTo-Json -Depth 5 -Compress)"
            }
            $results += [PSCustomObject]@{
                MachineName  = $parsed.MachineName
                MachineType  = $parsed.MachineType
                ResourceId   = $machineRid
                Status       = 'Error'
                OperationUrl = $null
                Result       = if ($errDetail) { $errDetail } else { $errMsg }
            }
        }
    }

    return $results
}
