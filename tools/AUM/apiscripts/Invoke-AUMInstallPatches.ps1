<#
.SYNOPSIS
    Triggers Azure Update Manager patch installation on one or more machines.
.DESCRIPTION
    Calls the AUM installPatches REST API to install updates on Azure VMs and
    Arc-enabled hybrid machines. Supports both Windows and Linux with appropriate
    classification and package/KB filtering options.
.PARAMETER SubscriptionId
    Azure subscription ID. If omitted, uses the current az CLI subscription.
.PARAMETER ResourceGroup
    Resource group containing the target machines.
.PARAMETER MachineName
    One or more machine names to patch. Accepts pipeline input.
.PARAMETER MachineType
    Machine type: AzureVM (default) or Arc (for hybrid/on-prem machines).
.PARAMETER ResourceId
    One or more full resource IDs. Supports both Microsoft.Compute/virtualMachines
    and Microsoft.HybridCompute/machines. Alternative to SubscriptionId/ResourceGroup/MachineName.
.PARAMETER OSType
    Operating system type: Windows or Linux.
.PARAMETER Classifications
    Update classifications to install.
    Windows: Critical, Security, UpdateRollup, FeaturePack, ServicePack, Definition, Tools, Updates
    Linux: Critical, Security, Other
.PARAMETER MaximumDuration
    Maximum time for the operation in ISO 8601 duration format. Default: PT2H (2 hours).
.PARAMETER RebootSetting
    Reboot behaviour: IfRequired (default), NeverReboot, AlwaysReboot.
.PARAMETER KBsToInclude
    (Windows only) List of KB IDs to include.
.PARAMETER KBsToExclude
    (Windows only) List of KB IDs to exclude.
.PARAMETER PackagesToInclude
    (Linux only) Package name masks to include.
.PARAMETER PackagesToExclude
    (Linux only) Package name masks to exclude.
.PARAMETER MaxPatchPublishDate
    Only install patches published on or before this date (yyyy-MM-ddTHH:mm:ssZ).
.PARAMETER ClientId
    Application (client) ID for service principal authentication.
.PARAMETER ClientSecret
    Client secret for service principal authentication.
.PARAMETER TenantId
    Azure AD tenant ID for service principal authentication.
.PARAMETER NoWait
    Return immediately without waiting for installation to complete.
.PARAMETER MaxWaitSeconds
    Maximum seconds to wait for completion. Default: 3600 (1 hour).
.EXAMPLE
    # Install critical & security patches on a Windows VM
    .\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxx" -ResourceGroup "myRG" -MachineName "myVM" `
        -OSType Windows -Classifications Critical,Security
.EXAMPLE
    # Install patches on an Arc-enabled hybrid machine
    .\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxx" -ResourceGroup "myRG" -MachineName "onpremServer" `
        -MachineType Arc -OSType Windows -Classifications Security
.EXAMPLE
    # Install all security patches on a Linux VM, no reboot
    .\Invoke-AUMInstallPatches.ps1 -SubscriptionId "xxx" -ResourceGroup "myRG" -MachineName "linuxVM" `
        -OSType Linux -Classifications Security -RebootSetting NeverReboot
.EXAMPLE
    # Using resource ID with service principal auth (auto-detects machine type)
    .\Invoke-AUMInstallPatches.ps1 -ResourceId "/subscriptions/.../Microsoft.HybridCompute/machines/myArcServer" `
        -OSType Windows -Classifications Security `
        -ClientId $appId -ClientSecret $secret -TenantId $tid
#>
[CmdletBinding(DefaultParameterSetName = 'ByName_AzCli', SupportsShouldProcess)]
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

    [Parameter(Mandatory)]
    [ValidateSet('Windows', 'Linux')]
    [string]$OSType,

    [Parameter(Mandatory)]
    [string[]]$Classifications,

    [ValidatePattern('^PT\d+[HM]$')]
    [string]$MaximumDuration = 'PT2H',

    [ValidateSet('IfRequired', 'NeverReboot', 'AlwaysReboot')]
    [string]$RebootSetting = 'IfRequired',

    [string[]]$KBsToInclude,
    [string[]]$KBsToExclude,
    [string[]]$PackagesToInclude,
    [string[]]$PackagesToExclude,
    [string]$MaxPatchPublishDate,

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

    [int]$MaxWaitSeconds = 3600
)

begin {
    $ErrorActionPreference = 'Stop'
    Import-Module "$PSScriptRoot\AUM-ApiCommon.psm1" -Force

    # Validate OS-specific parameters
    $validWindowsClassifications = @('Critical', 'Security', 'UpdateRollup', 'FeaturePack', 'ServicePack', 'Definition', 'Tools', 'Updates')
    $validLinuxClassifications = @('Critical', 'Security', 'Other')

    # Expand "All" shortcut to every classification for the OS
    if ($Classifications.Count -eq 1 -and $Classifications[0] -eq 'All') {
        if ($OSType -eq 'Windows') {
            $Classifications = $validWindowsClassifications
        }
        else {
            $Classifications = $validLinuxClassifications
        }
        Write-Host "  Expanded 'All' to: $($Classifications -join ', ')"
    }

    if ($OSType -eq 'Windows') {
        foreach ($c in $Classifications) {
            if ($c -notin $validWindowsClassifications) {
                throw "Invalid Windows classification: '$c'. Valid values: All, $($validWindowsClassifications -join ', ')"
            }
        }
        if ($PackagesToInclude -or $PackagesToExclude) {
            throw "PackagesToInclude/PackagesToExclude are only valid for Linux VMs."
        }
    }
    else {
        foreach ($c in $Classifications) {
            if ($c -notin $validLinuxClassifications) {
                throw "Invalid Linux classification: '$c'. Valid values: All, $($validLinuxClassifications -join ', ')"
            }
        }
        # Azure requires Critical and Security to be specified together on Linux
        $hasCritical = 'Critical' -in $Classifications
        $hasSecurity = 'Security' -in $Classifications
        if ($hasCritical -xor $hasSecurity) {
            Write-Warning "Linux requires Critical and Security together. Auto-adding the missing classification."
            $Classifications = @($Classifications)
            if ($hasCritical -and -not $hasSecurity) { $Classifications += 'Security' }
            if ($hasSecurity -and -not $hasCritical) { $Classifications += 'Critical' }
        }
        if ($KBsToInclude -or $KBsToExclude) {
            throw "KBsToInclude/KBsToExclude are only valid for Windows VMs."
        }
    }

    # Build request body
    $body = @{
        maximumDuration = $MaximumDuration
        rebootSetting   = $RebootSetting
    }

    if ($OSType -eq 'Windows') {
        $winParams = @{
            classificationsToInclude = @($Classifications)
        }
        if ($KBsToInclude)  { $winParams.kbNumbersToInclude = @($KBsToInclude) }
        if ($KBsToExclude)  { $winParams.kbNumbersToExclude = @($KBsToExclude) }
        $body.windowsParameters = $winParams
    }
    else {
        $linuxParams = @{
            classificationsToInclude = @($Classifications)
        }
        if ($PackagesToInclude) { $linuxParams.packageNameMasksToInclude = @($PackagesToInclude) }
        if ($PackagesToExclude) { $linuxParams.packageNameMasksToExclude = @($PackagesToExclude) }
        $body.linuxParameters = $linuxParams
    }

    if ($MaxPatchPublishDate) {
        $body.maxPatchPublishDate = $MaxPatchPublishDate
    }

    # Acquire token
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

        if (-not $PSCmdlet.ShouldProcess("$typeLabel $($parsed.MachineName) [$($parsed.ResourceGroup)]", "Install patches ($($Classifications -join ', '))")) {
            continue
        }

        Write-Host "Installing patches on $typeLabel`: $($parsed.MachineName) [$($parsed.ResourceGroup)]"

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

        Write-Host "  Classifications: $($Classifications -join ', ') | Reboot: $RebootSetting | Duration: $MaximumDuration"

        $uri = "https://management.azure.com$machineRid/installPatches?api-version=$apiVersion"
        Write-Verbose "POST $uri"
        Write-Verbose "Body: $($body | ConvertTo-Json -Depth 5 -Compress)"

        try {
            $response = Invoke-AUMRestMethod -Method POST -Uri $uri -Token $token -Body $body

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
                Write-Host "  Installation triggered (not waiting). Operation URL saved."
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
                $installed = $opResult.properties.installedPatchCount ?? $opResult.installedPatchCount ?? 'N/A'
                $pending   = $opResult.properties.pendingPatchCount ?? $opResult.pendingPatchCount ?? 'N/A'
                $reboot    = $opResult.properties.rebootStatus ?? $opResult.rebootStatus ?? 'N/A'
                Write-Host "  Patching complete: $installed installed, $pending pending, reboot=$reboot"
            }
            else {
                Write-Host "  Patching finished with status: $status"
            }
        }
        catch {
            $errMsg = $_.Exception.Message
            $errDetail = $null
            if ($_.ResponseBody) { $errDetail = $_.ResponseBody }
            elseif ($_.ErrorRecord.ResponseBody) { $errDetail = $_.ErrorRecord.ResponseBody }
            Write-Warning "Failed to install patches on $($parsed.MachineName): $errMsg"
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
