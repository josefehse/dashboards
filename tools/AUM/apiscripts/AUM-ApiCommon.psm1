#Requires -Version 7.0
<#
.SYNOPSIS
    Shared helper module for Azure Update Manager REST API scripts.
.DESCRIPTION
    Provides authentication (az CLI / service principal), REST API invocation,
    async operation polling, and resource-ID utilities.
#>

# --- Token Acquisition ---

function Get-AUMToken {
    <#
    .SYNOPSIS
        Gets an Azure Resource Manager bearer token.
    .DESCRIPTION
        Supports two authentication modes:
        - AzCli (default): uses the current az CLI session
        - ServicePrincipal: OAuth2 client_credentials flow
    .PARAMETER ClientId
        Application (client) ID for service principal auth.
    .PARAMETER ClientSecret
        Client secret for service principal auth.
    .PARAMETER TenantId
        Azure AD tenant ID for service principal auth.
    .EXAMPLE
        # Current user via az CLI
        $token = Get-AUMToken
    .EXAMPLE
        # Service principal
        $token = Get-AUMToken -ClientId $id -ClientSecret $secret -TenantId $tid
    #>
    [CmdletBinding(DefaultParameterSetName = 'AzCli')]
    param(
        [Parameter(ParameterSetName = 'ServicePrincipal', Mandatory)]
        [string]$ClientId,

        [Parameter(ParameterSetName = 'ServicePrincipal', Mandatory)]
        [string]$ClientSecret,

        [Parameter(ParameterSetName = 'ServicePrincipal', Mandatory)]
        [string]$TenantId
    )

    if ($PSCmdlet.ParameterSetName -eq 'ServicePrincipal') {
        $tokenUri = "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token"
        $body = @{
            grant_type    = 'client_credentials'
            client_id     = $ClientId
            client_secret = $ClientSecret
            scope         = 'https://management.azure.com/.default'
        }
        try {
            $response = Invoke-RestMethod -Uri $tokenUri -Method POST -Body $body -ContentType 'application/x-www-form-urlencoded'
            return $response.access_token
        }
        catch {
            throw "Failed to acquire token via client credentials: $($_.Exception.Message)"
        }
    }
    else {
        # AzCli mode
        try {
            $tokenJson = az account get-access-token --resource https://management.azure.com --output json 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "az CLI returned exit code $LASTEXITCODE. Ensure you are logged in (az login)."
            }
            $tokenObj = $tokenJson | ConvertFrom-Json
            return $tokenObj.accessToken
        }
        catch {
            throw "Failed to get token from az CLI: $($_.Exception.Message)"
        }
    }
}

function Get-AUMCurrentSubscription {
    <#
    .SYNOPSIS
        Gets the current subscription ID from az CLI.
    .OUTPUTS
        String - The subscription ID of the active az CLI account.
    #>
    [CmdletBinding()]
    param()

    try {
        $accountJson = az account show --output json 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "az CLI returned exit code $LASTEXITCODE. Ensure you are logged in (az login)."
        }
        $account = $accountJson | ConvertFrom-Json
        return $account.id
    }
    catch {
        throw "Failed to get current subscription from az CLI: $($_.Exception.Message)"
    }
}

# --- REST API Wrapper ---

function Invoke-AUMRestMethod {
    <#
    .SYNOPSIS
        Calls an Azure REST API and returns both the response body and headers.
    .DESCRIPTION
        Uses Invoke-WebRequest to preserve status codes and headers needed
        for async operation polling.
    .OUTPUTS
        PSObject with StatusCode, Headers, and Body properties.
    #>
    [CmdletBinding()]
    param(
        [ValidateSet('GET', 'POST', 'PUT', 'DELETE', 'PATCH')]
        [string]$Method = 'GET',

        [Parameter(Mandatory)]
        [string]$Uri,

        [Parameter(Mandatory)]
        [string]$Token,

        [object]$Body = $null,

        [int]$TimeoutSec = 120
    )

    $headers = @{
        'Authorization' = "Bearer $Token"
        'Content-Type'  = 'application/json'
    }

    $params = @{
        Uri                = $Uri
        Method             = $Method
        Headers            = $headers
        UseBasicParsing    = $true
        TimeoutSec         = $TimeoutSec
    }

    if ($Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 10)
    }

    try {
        $response = Invoke-WebRequest @params
    }
    catch {
        # Extract the response body from failed requests for detailed error info
        $errorBody = $null
        $statusCode = $null
        $rawError = $null

        # PowerShell 7: ErrorDetails.Message contains the response body
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $rawError = $_.ErrorDetails.Message
        }

        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            # Fallback: try reading from the response stream (PS 5.1 / Windows PowerShell)
            if (-not $rawError) {
                try {
                    $errorStream = $_.Exception.Response.GetResponseStream()
                    if ($errorStream -and $errorStream.CanRead) {
                        $reader = [System.IO.StreamReader]::new($errorStream)
                        $rawError = $reader.ReadToEnd()
                        $reader.Close()
                    }
                } catch {}
            }
        }

        if ($rawError) {
            try { $errorBody = $rawError | ConvertFrom-Json } catch { $errorBody = $rawError }
        }

        $detail = ''
        if ($errorBody.error.message) {
            $detail = $errorBody.error.message
        }
        elseif ($errorBody.error.code) {
            $detail = $errorBody.error.code
        }
        elseif ($errorBody.message) {
            $detail = $errorBody.message
        }
        elseif ($errorBody -is [string] -and $errorBody) {
            $detail = $errorBody
        }

        $msg = "HTTP $statusCode"
        if ($detail) { $msg += ": $detail" }
        else { $msg += ": $($_.Exception.Message)" }

        $ex = [System.Exception]::new($msg)
        $errorRecord = [System.Management.Automation.ErrorRecord]::new(
            $ex, 'AUMRestMethodFailed', [System.Management.Automation.ErrorCategory]::InvalidOperation, $Uri
        )
        # Attach the parsed error body for callers that want structured details
        $errorRecord | Add-Member -NotePropertyName 'ResponseBody' -NotePropertyValue $errorBody
        $errorRecord | Add-Member -NotePropertyName 'HttpStatusCode' -NotePropertyValue $statusCode
        throw $errorRecord
    }

    $responseBody = $null
    if ($response.Content) {
        try { $responseBody = $response.Content | ConvertFrom-Json } catch { $responseBody = $response.Content }
    }

    return [PSCustomObject]@{
        StatusCode = $response.StatusCode
        Headers    = $response.Headers
        Body       = $responseBody
    }
}

# --- Async Operation Polling ---

function Wait-AUMAsyncOperation {
    <#
    .SYNOPSIS
        Polls an Azure async operation until completion.
    .PARAMETER Response
        The initial response from Invoke-AUMRestMethod (must contain Headers).
    .PARAMETER Token
        Bearer access token.
    .PARAMETER MaxWaitSeconds
        Maximum time to wait before giving up. Default: 600 (10 minutes).
    .PARAMETER DefaultPollIntervalSec
        Fallback poll interval when Retry-After is not provided. Default: 15.
    .OUTPUTS
        PSObject - The final operation result.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [PSCustomObject]$Response,

        [Parameter(Mandatory)]
        [string]$Token,

        [int]$MaxWaitSeconds = 600,

        [int]$DefaultPollIntervalSec = 15
    )

    # If the request completed synchronously, return immediately
    if ($Response.StatusCode -in @(200, 201)) {
        return $Response.Body
    }

    # Determine poll URL: prefer Azure-AsyncOperation, fall back to Location
    $pollUrl = $null
    $useLocationFinalGet = $false

    if ($Response.Headers['Azure-AsyncOperation']) {
        $pollUrl = ($Response.Headers['Azure-AsyncOperation'] | Select-Object -First 1)
    }
    elseif ($Response.Headers['Location']) {
        $pollUrl = ($Response.Headers['Location'] | Select-Object -First 1)
        $useLocationFinalGet = $true
    }

    if (-not $pollUrl) {
        Write-Warning "No async operation URL in response. Returning response body as-is."
        return $Response.Body
    }

    $elapsed = 0
    $attempt = 0

    while ($elapsed -lt $MaxWaitSeconds) {
        # Determine wait interval
        $retryAfter = $DefaultPollIntervalSec
        if ($Response.Headers['Retry-After']) {
            $ra = ($Response.Headers['Retry-After'] | Select-Object -First 1)
            if ([int]::TryParse($ra, [ref]$null)) {
                $retryAfter = [int]$ra
            }
        }

        Write-Verbose "Polling in $retryAfter seconds... (attempt $($attempt + 1), elapsed ${elapsed}s)"
        Start-Sleep -Seconds $retryAfter
        $elapsed += $retryAfter
        $attempt++

        try {
            $pollResponse = Invoke-AUMRestMethod -Method GET -Uri $pollUrl -Token $Token
        }
        catch {
            Write-Warning "Poll request failed: $($_.Exception.Message). Retrying..."
            continue
        }

        $status = $null
        if ($pollResponse.Body.status) {
            $status = $pollResponse.Body.status
        }
        elseif ($pollResponse.Body.properties.status) {
            $status = $pollResponse.Body.properties.status
        }

        $terminalStates = @('Succeeded', 'Failed', 'Canceled', 'Cancelled', 'CompletedWithWarnings')
        if ($status -and ($status -in $terminalStates)) {
            if ($status -in @('Failed', 'Canceled', 'Cancelled')) {
                $errorMsg = $pollResponse.Body.error.message ?? $pollResponse.Body.properties.error.message ?? 'Unknown error'
                Write-Warning "Operation $status`: $errorMsg"
            }
            return $pollResponse.Body
        }

        # For Location-based polling, a 200 means completion
        if ($useLocationFinalGet -and $pollResponse.StatusCode -eq 200) {
            return $pollResponse.Body
        }

        # Update Retry-After from poll response
        $Response = $pollResponse
    }

    Write-Warning "Operation did not complete within $MaxWaitSeconds seconds. Last poll URL: $pollUrl"
    return $pollResponse.Body
}

# --- Resource ID Utilities ---

# Supported machine provider patterns
$script:AzureVMPattern = '/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.Compute/virtualMachines/([^/]+)'
$script:ArcMachinePattern = '/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.HybridCompute/machines/([^/]+)'

function ConvertTo-MachineResourceId {
    <#
    .SYNOPSIS
        Builds a machine resource ID from components, or validates an existing one.
        Supports both Azure VMs and Arc-enabled hybrid machines.
    .PARAMETER MachineType
        The machine type: AzureVM (default) or Arc.
    #>
    [CmdletBinding(DefaultParameterSetName = 'Components')]
    param(
        [Parameter(ParameterSetName = 'Components', Mandatory)]
        [string]$SubscriptionId,

        [Parameter(ParameterSetName = 'Components', Mandatory)]
        [string]$ResourceGroup,

        [Parameter(ParameterSetName = 'Components', Mandatory)]
        [string]$MachineName,

        [Parameter(ParameterSetName = 'Components')]
        [ValidateSet('AzureVM', 'Arc')]
        [string]$MachineType = 'AzureVM',

        [Parameter(ParameterSetName = 'ResourceId', Mandatory, ValueFromPipeline)]
        [string]$ResourceId
    )

    process {
        if ($PSCmdlet.ParameterSetName -eq 'ResourceId') {
            if ($ResourceId -match $script:AzureVMPattern -or $ResourceId -match $script:ArcMachinePattern) {
                return $ResourceId
            }
            throw "Invalid machine resource ID: $ResourceId. Must be a Microsoft.Compute/virtualMachines or Microsoft.HybridCompute/machines resource."
        }

        if ($MachineType -eq 'Arc') {
            return "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.HybridCompute/machines/$MachineName"
        }
        return "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Compute/virtualMachines/$MachineName"
    }
}

function Split-MachineResourceId {
    <#
    .SYNOPSIS
        Parses a machine resource ID into its components.
        Supports both Azure VMs and Arc-enabled hybrid machines.
    .OUTPUTS
        PSObject with SubscriptionId, ResourceGroup, MachineName, MachineType, and ResourceId.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [string]$ResourceId
    )

    process {
        if ($ResourceId -match $script:AzureVMPattern) {
            return [PSCustomObject]@{
                SubscriptionId = $Matches[1]
                ResourceGroup  = $Matches[2]
                MachineName    = $Matches[3]
                MachineType    = 'AzureVM'
                ResourceId     = $ResourceId
            }
        }
        if ($ResourceId -match $script:ArcMachinePattern) {
            return [PSCustomObject]@{
                SubscriptionId = $Matches[1]
                ResourceGroup  = $Matches[2]
                MachineName    = $Matches[3]
                MachineType    = 'Arc'
                ResourceId     = $ResourceId
            }
        }
        throw "Could not parse machine resource ID: $ResourceId"
    }
}

function Get-AUMApiVersion {
    <#
    .SYNOPSIS
        Returns the appropriate API version based on machine type.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateSet('AzureVM', 'Arc')]
        [string]$MachineType
    )

    switch ($MachineType) {
        'AzureVM' { return '2024-07-01' }
        'Arc'     { return '2020-08-15-preview' }
    }
}

# --- Machine State Checks ---

function Get-MachineRunningState {
    <#
    .SYNOPSIS
        Checks whether a machine is in a running state.
    .DESCRIPTION
        For Azure VMs, queries the instance view for PowerState.
        For Arc machines, queries the machine status for connected state.
    .OUTPUTS
        PSObject with IsRunning (bool), State (string), and Detail (string).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ResourceId,

        [Parameter(Mandatory)]
        [ValidateSet('AzureVM', 'Arc')]
        [string]$MachineType,

        [Parameter(Mandatory)]
        [string]$Token
    )

    if ($MachineType -eq 'AzureVM') {
        $apiVersion = Get-AUMApiVersion -MachineType AzureVM
        $uri = "https://management.azure.com$ResourceId/instanceView?api-version=$apiVersion"
        try {
            $response = Invoke-AUMRestMethod -Method GET -Uri $uri -Token $Token
            $powerStatus = $response.Body.statuses | Where-Object { $_.code -like 'PowerState/*' } | Select-Object -First 1
            $state = $powerStatus.displayStatus ?? 'Unknown'
            return [PSCustomObject]@{
                IsRunning = ($state -match 'running')
                State     = $state
                Detail    = $powerStatus.code
            }
        }
        catch {
            return [PSCustomObject]@{
                IsRunning = $false
                State     = 'Unknown'
                Detail    = $_.Exception.Message
            }
        }
    }
    else {
        # Arc machine — check agent status
        $apiVersion = Get-AUMApiVersion -MachineType Arc
        $uri = "https://management.azure.com$ResourceId`?api-version=$apiVersion"
        try {
            $response = Invoke-AUMRestMethod -Method GET -Uri $uri -Token $Token
            $agentStatus = $response.Body.properties.status ?? 'Unknown'
            return [PSCustomObject]@{
                IsRunning = ($agentStatus -eq 'Connected')
                State     = $agentStatus
                Detail    = $response.Body.properties.lastStatusChange
            }
        }
        catch {
            return [PSCustomObject]@{
                IsRunning = $false
                State     = 'Unknown'
                Detail    = $_.Exception.Message
            }
        }
    }
}

# --- Exports ---
Export-ModuleMember -Function @(
    'Get-AUMToken'
    'Get-AUMCurrentSubscription'
    'Invoke-AUMRestMethod'
    'Wait-AUMAsyncOperation'
    'ConvertTo-MachineResourceId'
    'Split-MachineResourceId'
    'Get-AUMApiVersion'
    'Get-MachineRunningState'
)
