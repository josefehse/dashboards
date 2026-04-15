param(
    [Parameter(Mandatory = $false)]
    [object] $WebhookData,

    [Parameter(Mandatory = $false)]
    [bool] $Test = $false
)

# --- Test mode: parse JSON input when testing manually ---
if ($Test) {
    $WebhookData = $WebhookData | ConvertFrom-Json
}

# --- Helper function to get Managed Identity token ---
function Get-ManagedIdentityToken {
    param([string]$Resource = "https://management.azure.com/")
    
    $tokenEndpoint = $env:IDENTITY_ENDPOINT
    $tokenHeader = $env:IDENTITY_HEADER
    
    if ($tokenEndpoint -and $tokenHeader) {
        # Azure Automation managed identity
        $headers = @{ "X-IDENTITY-HEADER" = $tokenHeader }
        $uri = "$tokenEndpoint`?resource=$Resource&api-version=2019-08-01"
        $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
        return $response.access_token
    } else {
        throw "Managed Identity environment variables not found. Ensure runbook is running in Azure Automation with Managed Identity enabled."
    }
}

# --- Helper function to call Azure REST API ---
function Invoke-AzureRestApi {
    param(
        [string]$Method = "GET",
        [string]$Uri,
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

# --- Guardrails: must be a webhook invocation with a JSON body ---
if (-not $WebhookData -or -not $WebhookData.RequestBody) {
    Write-Output "No WebhookData.RequestBody found. This runbook is intended to be triggered by an Azure Automation Webhook."
    return
}

# Parse the Event Grid payload
$payload = $null
try {
    $payload = ConvertFrom-Json -InputObject $WebhookData.RequestBody
} catch {
    Write-Output "Failed to parse RequestBody as JSON. Raw body:"
    Write-Output $WebhookData.RequestBody
    throw
}

# Event Grid can deliver a single event or an array of events
$events = @()
if ($payload -is [System.Collections.IEnumerable] -and -not ($payload -is [string])) {
    $events = @($payload)
} else {
    $events = @($payload)
}

# --- Validate event type(s) ---
$allowedEventTypes = @(
    "Microsoft.Maintenance.PreMaintenanceEvent",
    "Microsoft.Maintenance.PostMaintenanceEvent"
)

# Collect VM resourceIds from all events
$vmResourceIds = New-Object System.Collections.Generic.HashSet[string]

foreach ($evt in $events) {
    $eventType = $evt.eventType
    if (-not $eventType) {
        $eventType = $evt.type
    }

    if (-not $allowedEventTypes.Contains($eventType)) {
        Write-Output "Skipping event: not a maintenance pre/post event. eventType='$eventType'"
        continue
    }

    # This runbook handles PostMaintenance only (stop after patching completes)
    if ($eventType -ne "Microsoft.Maintenance.PostMaintenanceEvent") {
        Write-Output "Skipping eventType '$eventType' because this runbook handles PostMaintenance only."
        continue
    }

    # --- Extract resource IDs from payload ---
    $candidates = @()

    if ($evt.data -and $evt.data.resources) {
        $candidates += @($evt.data.resources)
    }
    if ($evt.subject) {
        $candidates += $evt.subject
    }
    if ($evt.data -and $evt.data.resourceId) {
        $candidates += $evt.data.resourceId
    }

    foreach ($c in $candidates) {
        if (-not $c) { continue }
        if ($c -match "/providers/Microsoft\.Compute/virtualMachines/") {
            [void]$vmResourceIds.Add($c)
        }
    }
}

if ($vmResourceIds.Count -eq 0) {
    Write-Output "No VM resourceIds in the event payload. Querying maintenance configuration for assigned machines..."

    # Extract the maintenance configuration resourceId from event data
    $maintenanceConfigId = $null
    foreach ($evt in $events) {
        if ($evt.data.MaintenanceConfigurationId) {
            $maintenanceConfigId = $evt.data.MaintenanceConfigurationId
            break
        }
        if ($evt.data.maintenanceConfigurationId) {
            $maintenanceConfigId = $evt.data.maintenanceConfigurationId
            break
        }
        # topic often contains the maintenance config path
        if ($evt.topic -and $evt.topic -match "/providers/[Mm]icrosoft\.[Mm]aintenance/maintenanceConfigurations/") {
            $maintenanceConfigId = $evt.topic
            break
        }
    }

    if (-not $maintenanceConfigId) {
        Write-Output "Could not find maintenance configuration ID in the event. Cannot query machines."
        Write-Output "Event payload for debugging:"
        $events | ConvertTo-Json -Depth 10 | Write-Output
        return
    }

    Write-Output "Maintenance Configuration: $maintenanceConfigId"

    # Get token for ARM and Resource Graph
    $token = Get-ManagedIdentityToken -Resource "https://management.azure.com/"

    # Query Azure Resource Graph for VMs assigned to this maintenance configuration
    $query = @"
maintenanceresources
| where type =~ "microsoft.maintenance/configurationassignments"
| where properties.maintenanceConfigurationId =~ "$maintenanceConfigId"
| where tolower(properties.resourceId) contains "microsoft.compute/virtualmachines"
| project vmResourceId = tostring(properties.resourceId)
"@

    Write-Output "Querying Resource Graph for assigned VMs..."
    
    # Extract subscription from maintenanceConfigId for scoping
    if ($maintenanceConfigId -match "/subscriptions/([^/]+)/") {
        $subscriptionId = $Matches[1]
    } else {
        Write-Output "Could not extract subscription ID from maintenance configuration."
        return
    }

    $rgUri = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    $rgBody = @{
        subscriptions = @($subscriptionId)
        query         = $query
    }

    try {
        $rgResults = Invoke-AzureRestApi -Method POST -Uri $rgUri -Token $token -Body $rgBody
        
        if ($rgResults.data -and $rgResults.data.Count -gt 0) {
            foreach ($row in $rgResults.data) {
                [void]$vmResourceIds.Add($row.vmResourceId)
            }
            Write-Output "Found $($vmResourceIds.Count) VMs from maintenance configuration assignments."
        } else {
            Write-Output "No direct VM assignments found. Checking for dynamic scopes..."
            
            # Query for dynamic scope assignments (subscription/RG level)
            $scopeQuery = @"
maintenanceresources
| where type =~ "microsoft.maintenance/configurationassignments"
| where properties.maintenanceConfigurationId =~ "$maintenanceConfigId"
| project scope = tostring(properties.resourceId), filter = properties.filter
"@
            $scopeBody = @{
                subscriptions = @($subscriptionId)
                query         = $scopeQuery
            }
            $scopeResults = Invoke-AzureRestApi -Method POST -Uri $rgUri -Token $token -Body $scopeBody

            foreach ($scope in $scopeResults.data) {
                # If scope is a subscription or resource group, query VMs within it
                if ($scope.scope -match "/subscriptions/[^/]+$" -or $scope.scope -match "/resourceGroups/[^/]+$") {
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
                    $vmResults = Invoke-AzureRestApi -Method POST -Uri $rgUri -Token $token -Body $vmBody
                    foreach ($vm in $vmResults.data) {
                        [void]$vmResourceIds.Add($vm.id)
                    }
                }
            }

            if ($vmResourceIds.Count -gt 0) {
                Write-Output "Found $($vmResourceIds.Count) VMs from dynamic scopes."
            } else {
                Write-Output "No VMs found in maintenance configuration. Nothing to stop."
                return
            }
        }
    } catch {
        Write-Output "Resource Graph query failed: $($_.Exception.Message)"
        throw
    }
}

Write-Output "VMs to stop (count=$($vmResourceIds.Count)):"
$vmResourceIds | ForEach-Object { Write-Output $_ }

# Get token if not already obtained
if (-not $token) {
    $token = Get-ManagedIdentityToken -Resource "https://management.azure.com/"
}

# Stop each VM using REST API (deallocate to stop billing)
foreach ($rid in $vmResourceIds) {
    try {
        # Get current power state
        $statusUri = "https://management.azure.com$rid/instanceView?api-version=2024-03-01"
        $vmStatus = Invoke-AzureRestApi -Method GET -Uri $statusUri -Token $token
        
        $powerState = ($vmStatus.statuses | Where-Object { $_.code -like "PowerState/*" } | Select-Object -First 1).displayStatus

        if ($powerState -and $powerState -match "deallocated|stopped") {
            Write-Output "VM '$rid' is already stopped/deallocated. Skipping."
            continue
        }

        # Deallocate the VM (async) - this stops the VM and releases compute resources
        $deallocateUri = "https://management.azure.com$rid/deallocate?api-version=2024-03-01"
        Write-Output "Stopping (deallocating) VM: $rid"
        Invoke-AzureRestApi -Method POST -Uri $deallocateUri -Token $token | Out-Null
        Write-Output "Stop initiated for: $rid"

    } catch {
        Write-Output "Failed to stop VM '$rid'. Error: $($_.Exception.Message)"
        throw
    }
}

Write-Output "Post-maintenance VM stop script completed."
