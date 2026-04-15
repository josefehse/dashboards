#Requires -Version 7.0
<#
.SYNOPSIS
    Shared helper functions for Azure Update Manager (AUM) maintenance event handling.

.DESCRIPTION
    This module provides common functions used by AUM pre/post maintenance Azure Functions:
    - Managed Identity token acquisition
    - Azure REST API wrapper
    - Event Grid event parsing
    - Resource Graph queries for VM discovery
    - VM power state helpers
#>

# --- Token Acquisition ---

function Get-ManagedIdentityToken {
    <#
    .SYNOPSIS
        Gets an access token using Azure Managed Identity.
    .PARAMETER Resource
        The resource URI to get a token for. Default: Azure Resource Manager.
    .OUTPUTS
        String - The access token.
    #>
    [CmdletBinding()]
    param(
        [string]$Resource = "https://management.azure.com/"
    )
    
    # Azure Functions managed identity (Flex Consumption / v4 runtime)
    $tokenEndpoint = $env:IDENTITY_ENDPOINT
    $tokenHeader = $env:IDENTITY_HEADER
    
    if ($tokenEndpoint -and $tokenHeader) {
        $headers = @{ "X-IDENTITY-HEADER" = $tokenHeader }
        $uri = "$tokenEndpoint`?resource=$Resource&api-version=2019-08-01"
        $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
        return $response.access_token
    }
    
    # Fallback for MSI_ENDPOINT (older runtime / App Service)
    $msiEndpoint = $env:MSI_ENDPOINT
    $msiSecret = $env:MSI_SECRET
    
    if ($msiEndpoint -and $msiSecret) {
        $headers = @{ "Secret" = $msiSecret }
        $uri = "$msiEndpoint`?resource=$Resource&api-version=2017-09-01"
        $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
        return $response.access_token
    }
    
    throw "Managed Identity not available. Ensure the Function App has a system-assigned or user-assigned managed identity enabled."
}

# --- REST API Wrapper ---

function Invoke-AzureRestApi {
    <#
    .SYNOPSIS
        Invokes an Azure REST API with bearer token authentication.
    .PARAMETER Method
        HTTP method (GET, POST, PUT, DELETE, PATCH).
    .PARAMETER Uri
        Full URI of the REST endpoint.
    .PARAMETER Token
        Bearer access token.
    .PARAMETER Body
        Optional request body (will be converted to JSON).
    .OUTPUTS
        PSObject - Deserialized JSON response.
    #>
    [CmdletBinding()]
    param(
        [ValidateSet("GET", "POST", "PUT", "DELETE", "PATCH")]
        [string]$Method = "GET",
        
        [Parameter(Mandatory)]
        [string]$Uri,
        
        [Parameter(Mandatory)]
        [string]$Token,
        
        [object]$Body = $null
    )
    
    $headers = @{
        "Authorization" = "Bearer $Token"
        "Content-Type"  = "application/json"
    }
    
    $params = @{
        Uri     = $Uri
        Method  = $Method
        Headers = $headers
    }
    
    if ($Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 10)
    }
    
    return Invoke-RestMethod @params
}

# --- Resource ID Parsing ---

function ConvertFrom-VMResourceId {
    <#
    .SYNOPSIS
        Parses a VM resource ID into its components.
    .PARAMETER ResourceId
        Full Azure resource ID of a virtual machine.
    .OUTPUTS
        PSObject with SubscriptionId, ResourceGroup, Name, and original Id.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [string]$ResourceId
    )
    
    process {
        if ($ResourceId -match '/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.Compute/virtualMachines/([^/]+)') {
            return [PSCustomObject]@{
                SubscriptionId = $Matches[1]
                ResourceGroup  = $Matches[2]
                Name           = $Matches[3]
                Id             = $ResourceId
            }
        }
        
        Write-Warning "Could not parse VM resource ID: $ResourceId"
        return $null
    }
}

function Get-SubscriptionIdFromResourceId {
    <#
    .SYNOPSIS
        Extracts the subscription ID from any Azure resource ID.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ResourceId
    )
    
    if ($ResourceId -match '/subscriptions/([^/]+)/') {
        return $Matches[1]
    }
    return $null
}

# --- Event Grid Event Parsing ---

function Get-MaintenanceConfigurationId {
    <#
    .SYNOPSIS
        Extracts the maintenance configuration ID from an Event Grid event.
    .PARAMETER Event
        The Event Grid event object.
    .OUTPUTS
        String - The maintenance configuration resource ID, or $null if not found.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Event
    )
    
    # Try various locations where the maintenance config ID might appear
    if ($Event.data.MaintenanceConfigurationId) {
        return $Event.data.MaintenanceConfigurationId
    }
    if ($Event.data.maintenanceConfigurationId) {
        return $Event.data.maintenanceConfigurationId
    }
    if ($Event.topic -and $Event.topic -match '/providers/[Mm]icrosoft\.[Mm]aintenance/maintenanceConfigurations/') {
        return $Event.topic
    }
    
    return $null
}

function Get-VMResourceIdsFromEvent {
    <#
    .SYNOPSIS
        Extracts VM resource IDs directly from an Event Grid event payload.
    .PARAMETER Event
        The Event Grid event object.
    .OUTPUTS
        HashSet[string] - Unique VM resource IDs found in the event.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Event
    )
    
    $vmResourceIds = New-Object System.Collections.Generic.HashSet[string]
    
    $candidates = @()
    if ($Event.data -and $Event.data.resources) {
        $candidates += @($Event.data.resources)
    }
    if ($Event.subject) {
        $candidates += $Event.subject
    }
    if ($Event.data -and $Event.data.resourceId) {
        $candidates += $Event.data.resourceId
    }
    
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        if ($c -match '/providers/Microsoft\.Compute/virtualMachines/') {
            [void]$vmResourceIds.Add($c)
        }
    }
    
    return $vmResourceIds
}

# --- Resource Graph Queries ---

function Get-VMsFromMaintenanceConfiguration {
    <#
    .SYNOPSIS
        Queries Azure Resource Graph to find VMs assigned to a maintenance configuration.
    .PARAMETER MaintenanceConfigurationId
        The resource ID of the maintenance configuration.
    .PARAMETER Token
        Bearer access token for Azure Resource Manager.
    .OUTPUTS
        HashSet[string] - VM resource IDs assigned to the configuration.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$MaintenanceConfigurationId,
        
        [Parameter(Mandatory)]
        [string]$Token
    )
    
    $vmResourceIds = New-Object System.Collections.Generic.HashSet[string]
    
    $subscriptionId = Get-SubscriptionIdFromResourceId -ResourceId $MaintenanceConfigurationId
    if (-not $subscriptionId) {
        Write-Warning "Could not extract subscription ID from maintenance configuration."
        return $vmResourceIds
    }
    
    $rgUri = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    
    # Query for direct VM assignments
    $directQuery = @"
maintenanceresources
| where type =~ "microsoft.maintenance/configurationassignments"
| where properties.maintenanceConfigurationId =~ "$MaintenanceConfigurationId"
| where tolower(properties.resourceId) contains "microsoft.compute/virtualmachines"
| project vmResourceId = tostring(properties.resourceId)
"@
    
    $rgBody = @{
        subscriptions = @($subscriptionId)
        query         = $directQuery
    }
    
    Write-Host "Querying Resource Graph for directly assigned VMs..."
    $rgResults = Invoke-AzureRestApi -Method POST -Uri $rgUri -Token $Token -Body $rgBody
    
    if ($rgResults.data -and $rgResults.data.Count -gt 0) {
        foreach ($row in $rgResults.data) {
            [void]$vmResourceIds.Add($row.vmResourceId)
        }
        Write-Host "Found $($vmResourceIds.Count) VMs from direct assignments."
        return $vmResourceIds
    }
    
    # Fallback: Check for dynamic scopes (subscription/RG level assignments)
    Write-Host "No direct VM assignments. Checking for dynamic scopes..."
    
    $scopeQuery = @"
maintenanceresources
| where type =~ "microsoft.maintenance/configurationassignments"
| where properties.maintenanceConfigurationId =~ "$MaintenanceConfigurationId"
| project scope = tostring(properties.resourceId), filter = properties.filter
"@
    
    $scopeBody = @{
        subscriptions = @($subscriptionId)
        query         = $scopeQuery
    }
    
    $scopeResults = Invoke-AzureRestApi -Method POST -Uri $rgUri -Token $Token -Body $scopeBody
    
    foreach ($scope in $scopeResults.data) {
        # If scope is at subscription or resource group level, query VMs within it
        if ($scope.scope -match '/subscriptions/[^/]+$' -or $scope.scope -match '/resourceGroups/[^/]+$') {
            $vmQuery = @"
resources
| where type =~ "microsoft.compute/virtualmachines"
| where id startswith "$($scope.scope)"
| project id
"@
            $vmBody = @{
                subscriptions = @($subscriptionId)
                query         = $vmQuery
            }
            $vmResults = Invoke-AzureRestApi -Method POST -Uri $rgUri -Token $Token -Body $vmBody
            foreach ($vm in $vmResults.data) {
                [void]$vmResourceIds.Add($vm.id)
            }
        }
    }
    
    if ($vmResourceIds.Count -gt 0) {
        Write-Host "Found $($vmResourceIds.Count) VMs from dynamic scopes."
    }
    
    return $vmResourceIds
}

function Get-MaintenanceEventVMs {
    <#
    .SYNOPSIS
        Gets all VM resource IDs affected by a maintenance event.
        First tries to extract from event payload, then queries Resource Graph.
    .PARAMETER Event
        The Event Grid event object.
    .PARAMETER Token
        Bearer access token for Azure Resource Manager.
    .OUTPUTS
        HashSet[string] - VM resource IDs to process.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Event,
        
        [Parameter(Mandatory)]
        [string]$Token
    )
    
    # First, try to get VMs directly from the event payload
    $vmResourceIds = Get-VMResourceIdsFromEvent -Event $Event
    
    if ($vmResourceIds.Count -gt 0) {
        Write-Host "Found $($vmResourceIds.Count) VM(s) in event payload."
        return $vmResourceIds
    }
    
    # No VMs in payload - query maintenance configuration
    Write-Host "No VMs in event payload. Querying maintenance configuration..."
    
    $maintenanceConfigId = Get-MaintenanceConfigurationId -Event $Event
    if (-not $maintenanceConfigId) {
        Write-Warning "Could not find maintenance configuration ID in event."
        Write-Host "Event data: $($Event | ConvertTo-Json -Depth 5)"
        return $vmResourceIds  # Empty set
    }
    
    Write-Host "Maintenance Configuration: $maintenanceConfigId"
    
    return Get-VMsFromMaintenanceConfiguration -MaintenanceConfigurationId $maintenanceConfigId -Token $Token
}

# --- VM Operations ---

function Get-VMPowerState {
    <#
    .SYNOPSIS
        Gets the current power state of a VM.
    .PARAMETER VMResourceId
        The VM resource ID.
    .PARAMETER Token
        Bearer access token.
    .OUTPUTS
        String - The power state display status (e.g., "VM running", "VM deallocated").
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$VMResourceId,
        
        [Parameter(Mandatory)]
        [string]$Token
    )
    
    $statusUri = "https://management.azure.com$VMResourceId/instanceView?api-version=2024-03-01"
    $vmStatus = Invoke-AzureRestApi -Method GET -Uri $statusUri -Token $Token
    
    $powerStatus = $vmStatus.statuses | Where-Object { $_.code -like "PowerState/*" } | Select-Object -First 1
    return $powerStatus.displayStatus
}

function Get-VMDetails {
    <#
    .SYNOPSIS
        Gets full VM details including disk information.
    .PARAMETER VMResourceId
        The VM resource ID.
    .PARAMETER Token
        Bearer access token.
    .OUTPUTS
        PSObject - The VM resource object.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$VMResourceId,
        
        [Parameter(Mandatory)]
        [string]$Token
    )
    
    $vmUri = "https://management.azure.com$VMResourceId`?api-version=2024-03-01"
    return Invoke-AzureRestApi -Method GET -Uri $vmUri -Token $Token
}

function Start-VMAsync {
    <#
    .SYNOPSIS
        Starts a VM asynchronously.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$VMResourceId,
        
        [Parameter(Mandatory)]
        [string]$Token
    )
    
    $startUri = "https://management.azure.com$VMResourceId/start?api-version=2024-03-01"
    Invoke-AzureRestApi -Method POST -Uri $startUri -Token $Token | Out-Null
}

function Stop-VMAsync {
    <#
    .SYNOPSIS
        Deallocates (stops) a VM asynchronously.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$VMResourceId,
        
        [Parameter(Mandatory)]
        [string]$Token
    )
    
    $deallocateUri = "https://management.azure.com$VMResourceId/deallocate?api-version=2024-03-01"
    Invoke-AzureRestApi -Method POST -Uri $deallocateUri -Token $Token | Out-Null
}

# --- Export Functions ---
Export-ModuleMember -Function @(
    'Get-ManagedIdentityToken'
    'Invoke-AzureRestApi'
    'ConvertFrom-VMResourceId'
    'Get-SubscriptionIdFromResourceId'
    'Get-MaintenanceConfigurationId'
    'Get-VMResourceIdsFromEvent'
    'Get-VMsFromMaintenanceConfiguration'
    'Get-MaintenanceEventVMs'
    'Get-VMPowerState'
    'Get-VMDetails'
    'Start-VMAsync'
    'Stop-VMAsync'
)
