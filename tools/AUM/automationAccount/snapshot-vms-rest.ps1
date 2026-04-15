param(
    [Parameter(Mandatory = $false)]
    [object] $WebhookData,

    [Parameter(Mandatory = $false)]
    [bool] $Test = $false,

    [Parameter(Mandatory = $false)]
    [string] $SnapshotResourceGroup = $null,  # If not specified, snapshots go to same RG as VM

    [Parameter(Mandatory = $false)]
    [string] $SnapshotNamePrefix = "premaint"
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

    if ($eventType -ne "Microsoft.Maintenance.PreMaintenanceEvent") {
        Write-Output "Skipping eventType '$eventType' because this runbook handles PreMaintenance only."
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

# Get token for ARM and Resource Graph
$token = Get-ManagedIdentityToken -Resource "https://management.azure.com/"

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
                Write-Output "No VMs found in maintenance configuration. Nothing to snapshot."
                return
            }
        }
    } catch {
        Write-Output "Resource Graph query failed: $($_.Exception.Message)"
        throw
    }
}

Write-Output "VMs to snapshot (count=$($vmResourceIds.Count)):"
$vmResourceIds | ForEach-Object { Write-Output $_ }

# --- Create snapshots for each VM's disks ---
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapshotResults = @()

foreach ($vmId in $vmResourceIds) {
    try {
        Write-Output "`n--- Processing VM: $vmId ---"

        # Parse VM resource ID components
        if ($vmId -match "/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.Compute/virtualMachines/([^/]+)") {
            $vmSubscriptionId = $Matches[1]
            $vmResourceGroup = $Matches[2]
            $vmName = $Matches[3]
        } else {
            Write-Output "Could not parse VM resource ID: $vmId"
            continue
        }

        # Get VM details to find attached disks
        $vmUri = "https://management.azure.com$vmId`?api-version=2024-03-01"
        $vm = Invoke-AzureRestApi -Method GET -Uri $vmUri -Token $token

        $vmLocation = $vm.location
        $disksToSnapshot = @()

        # OS Disk
        if ($vm.properties.storageProfile.osDisk.managedDisk) {
            $disksToSnapshot += @{
                DiskId   = $vm.properties.storageProfile.osDisk.managedDisk.id
                DiskName = $vm.properties.storageProfile.osDisk.name
                DiskType = "OSDisk"
            }
        }

        # Data Disks
        if ($vm.properties.storageProfile.dataDisks) {
            foreach ($dataDisk in $vm.properties.storageProfile.dataDisks) {
                if ($dataDisk.managedDisk) {
                    $disksToSnapshot += @{
                        DiskId   = $dataDisk.managedDisk.id
                        DiskName = $dataDisk.name
                        DiskType = "DataDisk-LUN$($dataDisk.lun)"
                    }
                }
            }
        }

        Write-Output "Found $($disksToSnapshot.Count) disk(s) to snapshot for VM '$vmName'."

        # Determine target resource group for snapshots
        $targetRg = if ($SnapshotResourceGroup) { $SnapshotResourceGroup } else { $vmResourceGroup }

        # Create snapshot for each disk
        foreach ($disk in $disksToSnapshot) {
            $snapshotName = "$SnapshotNamePrefix-$vmName-$($disk.DiskType)-$timestamp"
            
            # Ensure snapshot name is valid (max 80 chars, alphanumeric, underscores, hyphens, periods)
            $snapshotName = $snapshotName -replace '[^a-zA-Z0-9_\-\.]', '-'
            if ($snapshotName.Length -gt 80) {
                $snapshotName = $snapshotName.Substring(0, 80)
            }

            Write-Output "Creating snapshot '$snapshotName' for disk '$($disk.DiskName)'..."

            $snapshotUri = "https://management.azure.com/subscriptions/$vmSubscriptionId/resourceGroups/$targetRg/providers/Microsoft.Compute/snapshots/$snapshotName`?api-version=2024-03-02"

            $snapshotBody = @{
                location   = $vmLocation
                tags       = @{
                    "Maintenance" = "Patching"
                    "SourceVM"    = $vmName
                    "SourceDisk"  = $disk.DiskName
                    "DiskType"    = $disk.DiskType
                    "CreatedBy"   = "AUM-PreMaintenance-Snapshot"
                    "CreatedOn"   = $timestamp
                }
                properties = @{
                    creationData = @{
                        createOption     = "Copy"
                        sourceResourceId = $disk.DiskId
                    }
                    incremental  = $true  # Use incremental snapshots for cost efficiency
                }
            }

            try {
                $result = Invoke-AzureRestApi -Method PUT -Uri $snapshotUri -Token $token -Body $snapshotBody
                Write-Output "Snapshot creation initiated: $snapshotName"
                
                $snapshotResults += [PSCustomObject]@{
                    VMName       = $vmName
                    DiskName     = $disk.DiskName
                    DiskType     = $disk.DiskType
                    SnapshotName = $snapshotName
                    Status       = "Initiated"
                }
            } catch {
                Write-Output "Failed to create snapshot for disk '$($disk.DiskName)': $($_.Exception.Message)"
                $snapshotResults += [PSCustomObject]@{
                    VMName       = $vmName
                    DiskName     = $disk.DiskName
                    DiskType     = $disk.DiskType
                    SnapshotName = $snapshotName
                    Status       = "Failed: $($_.Exception.Message)"
                }
            }
        }

    } catch {
        Write-Output "Failed to process VM '$vmId': $($_.Exception.Message)"
        $snapshotResults += [PSCustomObject]@{
            VMName       = $vmId
            DiskName     = "N/A"
            DiskType     = "N/A"
            SnapshotName = "N/A"
            Status       = "Failed: $($_.Exception.Message)"
        }
    }
}

# --- Summary ---
Write-Output "`n=== Snapshot Summary ==="
Write-Output "Total VMs processed: $($vmResourceIds.Count)"
Write-Output "Total snapshots attempted: $($snapshotResults.Count)"
Write-Output ""

$succeeded = ($snapshotResults | Where-Object { $_.Status -eq "Initiated" }).Count
$failed = ($snapshotResults | Where-Object { $_.Status -like "Failed*" }).Count

Write-Output "Succeeded: $succeeded"
Write-Output "Failed: $failed"
Write-Output ""

$snapshotResults | Format-Table -AutoSize

Write-Output "`nPre-maintenance disk snapshot script completed."
