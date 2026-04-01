param(
    [Parameter(Mandatory = $false)]
    [object] $WebhookData
)

# --- Import required modules ---
#Import-Module Az.Accounts -ErrorAction Stop
Import-Module Az.ResourceGraph -ErrorAction Stop
#Import-Module Az.Compute -ErrorAction Stop

# --- Guardrails: must be a webhook invocation with a JSON body ---
if (-not $WebhookData -or -not $WebhookData.RequestBody) {
    Write-Output "No WebhookData.RequestBody found. This runbook is intended to be triggered by an Azure Automation Webhook."
    return
}

# Parse the Event Grid payload (AUM uses Event Grid for pre/post events)
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

# --- Validate event type(s) to avoid unintended triggers (Microsoft guidance) ---
# AUM tutorial recommends validating Microsoft.Maintenance.PreMaintenanceEvent / PostMaintenanceEvent 
$allowedEventTypes = @(
    "Microsoft.Maintenance.PreMaintenanceEvent",
    "Microsoft.Maintenance.PostMaintenanceEvent"
)

# Collect VM resourceIds from all events
$vmResourceIds = New-Object System.Collections.Generic.HashSet[string]

foreach ($evt in $events) {

    $eventType = $evt.eventType
    if (-not $eventType) {
        # Some Event Grid schemas can use "type" instead of "eventType" – be tolerant
        $eventType = $evt.type
    }

    if (-not $allowedEventTypes.Contains($eventType)) {
        Write-Output "Skipping event: not a maintenance pre/post event. eventType/type='$eventType'"
        continue
    }

    # If you want this runbook to be ONLY for PreMaintenance, uncomment:
    if ($eventType -ne "Microsoft.Maintenance.PreMaintenanceEvent") {
        Write-Output "Skipping eventType '$eventType' because this runbook handles PreMaintenance only."
        continue
    }

    # --- Extract resource IDs ---
    # Microsoft notes you may need to query for machine lists if not present, but first try payload. 
    # We look for common patterns defensively.
    $candidates = @()

    # Pattern A: evt.data.resources is an array of resourceIds (commonly used)
    if ($evt.data -and $evt.data.resources) {
        $candidates += @($evt.data.resources)
    }

    # Pattern B: evt.subject sometimes contains the resourceId-like path
    if ($evt.subject) {
        $candidates += $evt.subject
    }

    # Pattern C: evt.data.resourceId (single)
    if ($evt.data -and $evt.data.resourceId) {
        $candidates += $evt.data.resourceId
    }

    foreach ($c in $candidates) {
        if (-not $c) { continue }

        # Only keep Azure VM resourceIds
        # /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<name>
        if ($c -match "/providers/Microsoft\.Compute/virtualMachines/") {
            [void]$vmResourceIds.Add($c)
        }
    }
}

if ($vmResourceIds.Count -eq 0) {
    Write-Output "No VM resourceIds in the event payload. Querying maintenance configuration for assigned machines..."

    # Extract the maintenance configuration resourceId from the event subject or data
    $maintenanceConfigId = $null
    foreach ($evt in $events) {
        # The subject typically contains the maintenance configuration resource ID
        if ($evt.subject -and $evt.subject -match "/providers/Microsoft\.Maintenance/maintenanceConfigurations/") {
            $maintenanceConfigId = $evt.subject
            break
        }
        # Also check data.resourceUri or data.maintenanceConfigurationId
        if ($evt.data.resourceUri) {
            $maintenanceConfigId = $evt.data.resourceUri
            break
        }
        if ($evt.data.maintenanceConfigurationId) {
            $maintenanceConfigId = $evt.data.maintenanceConfigurationId
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

    # Authenticate before querying
    Connect-AzAccount -Identity | Out-Null

    # Query Azure Resource Graph for VMs assigned to this maintenance configuration
    $query = @"
maintenanceresources
| where type == "microsoft.maintenance/configurationassignments"
| where properties.maintenanceConfigurationId =~ "$maintenanceConfigId"
| where properties.resourceId contains "Microsoft.Compute/virtualMachines"
| project vmResourceId = tostring(properties.resourceId)
"@

    Write-Output "Querying Resource Graph for assigned VMs..."
    $rgResults = Search-AzGraph -Query $query -ErrorAction SilentlyContinue

    if ($rgResults -and $rgResults.Count -gt 0) {
        foreach ($row in $rgResults) {
            [void]$vmResourceIds.Add($row.vmResourceId)
        }
        Write-Output "Found $($vmResourceIds.Count) VMs from maintenance configuration assignments."
    } else {
        # Fallback: Check for dynamic scopes (resource groups, subscriptions, tags)
        Write-Output "No direct VM assignments found. Checking for dynamic scopes..."
        
        $scopeQuery = @"
maintenanceresources
| where type == "microsoft.maintenance/configurationassignments"
| where properties.maintenanceConfigurationId =~ "$maintenanceConfigId"
| project scope = tostring(properties.resourceId), filter = properties.filter
"@
        $scopes = Search-AzGraph -Query $scopeQuery -ErrorAction SilentlyContinue

        foreach ($scope in $scopes) {
            # If scope is a subscription or resource group, query VMs within it
            if ($scope.scope -match "/subscriptions/[^/]+$" -or $scope.scope -match "/resourceGroups/[^/]+$") {
                $vmQuery = @"
resources
| where type == "microsoft.compute/virtualmachines"
| where id startswith "$($scope.scope)"
| project id
"@
                $vms = Search-AzGraph -Query $vmQuery -ErrorAction SilentlyContinue
                foreach ($vm in $vms) {
                    [void]$vmResourceIds.Add($vm.id)
                }
            }
        }

        if ($vmResourceIds.Count -gt 0) {
            Write-Output "Found $($vmResourceIds.Count) VMs from dynamic scopes."
        } else {
            Write-Output "No VMs found in maintenance configuration. Nothing to start."
            return
        }
    }
}

Write-Output "VMs to start (count=$($vmResourceIds.Count)):"
$vmResourceIds | ForEach-Object { Write-Output $_ }

# --- Authenticate (Managed Identity recommended for Automation webhook runbooks) ---
# Check if already authenticated (from Resource Graph query path)
$context = Get-AzContext -ErrorAction SilentlyContinue
if (-not $context) {
    Connect-AzAccount -Identity | Out-Null
}

# Start each VM
foreach ($rid in $vmResourceIds) {
    try {
        $res = Get-AzResource -ResourceId $rid -ErrorAction Stop
        $rg  = $res.ResourceGroupName
        $name = $res.Name

        # Optional: check power state to be idempotent
        $vmStatus = Get-AzVM -ResourceGroupName $rg -Name $name -Status -ErrorAction Stop
        $powerState = ($vmStatus.Statuses | Where-Object { $_.Code -like "PowerState/*" } | Select-Object -First 1).DisplayStatus

        if ($powerState -and $powerState -match "running") {
            Write-Output "VM '$name' in RG '$rg' is already running. Skipping start."
            continue
        }

        Write-Output "Starting VM '$name' in RG '$rg'..."
        Start-AzVM -ResourceGroupName $rg -Name $name -NoWait -ErrorAction Stop | Out-Null
        Write-Output "Start initiated for '$name'."

    } catch {
        Write-Output "Failed to start VM resourceId='$rid'. Error: $($_.Exception.Message)"
        throw
    }
}