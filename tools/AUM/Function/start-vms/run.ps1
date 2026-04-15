# Input bindings are passed in via param block.
param($eventGridEvent, $TriggerMetadata)

Write-Host "Pre-maintenance VM start function triggered."
Write-Host "Event Type: $($eventGridEvent.eventType)"
Write-Host "Event Subject: $($eventGridEvent.subject)"

# --- Validate event type ---
if ($eventGridEvent.eventType -ne "Microsoft.Maintenance.PreMaintenanceEvent") {
    Write-Host "Skipping eventType '$($eventGridEvent.eventType)' - this function handles PreMaintenanceEvent only."
    return
}

# --- Get token and discover VMs ---
$token = Get-ManagedIdentityToken -Resource "https://management.azure.com/"

$vmResourceIds = Get-MaintenanceEventVMs -Event $eventGridEvent -Token $token

if ($vmResourceIds.Count -eq 0) {
    Write-Host "No VMs found to start."
    return
}

Write-Host "VMs to start (count=$($vmResourceIds.Count)):"
$vmResourceIds | ForEach-Object { Write-Host $_ }

# --- Start each VM ---
$started = 0
$skipped = 0
$failed = 0

foreach ($vmId in $vmResourceIds) {
    try {
        $powerState = Get-VMPowerState -VMResourceId $vmId -Token $token

        if ($powerState -and $powerState -match "running") {
            Write-Host "VM '$vmId' is already running. Skipping."
            $skipped++
            continue
        }

        Write-Host "Starting VM: $vmId"
        Start-VMAsync -VMResourceId $vmId -Token $token
        Write-Host "Start initiated for: $vmId"
        $started++

    } catch {
        Write-Host "Failed to start VM '$vmId'. Error: $($_.Exception.Message)"
        $failed++
    }
}

Write-Host "=== Summary ==="
Write-Host "VMs started: $started"
Write-Host "VMs skipped (already running): $skipped"
Write-Host "VMs failed: $failed"
Write-Host "Pre-maintenance VM start function completed."
