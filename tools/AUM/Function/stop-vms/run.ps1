# Input bindings are passed in via param block.
param($eventGridEvent, $TriggerMetadata)

Write-Host "Post-maintenance VM stop function triggered."
Write-Host "Event Type: $($eventGridEvent.eventType)"
Write-Host "Event Subject: $($eventGridEvent.subject)"

# --- Validate event type ---
if ($eventGridEvent.eventType -ne "Microsoft.Maintenance.PostMaintenanceEvent") {
    Write-Host "Skipping eventType '$($eventGridEvent.eventType)' - this function handles PostMaintenanceEvent only."
    return
}

# --- Get token and discover VMs ---
$token = Get-ManagedIdentityToken -Resource "https://management.azure.com/"

$vmResourceIds = Get-MaintenanceEventVMs -Event $eventGridEvent -Token $token

if ($vmResourceIds.Count -eq 0) {
    Write-Host "No VMs found to stop."
    return
}

Write-Host "VMs to stop (count=$($vmResourceIds.Count)):"
$vmResourceIds | ForEach-Object { Write-Host $_ }

# --- Stop (deallocate) each VM ---
$stopped = 0
$skipped = 0
$failed = 0

foreach ($vmId in $vmResourceIds) {
    try {
        $powerState = Get-VMPowerState -VMResourceId $vmId -Token $token

        if ($powerState -and $powerState -match "deallocated|stopped") {
            Write-Host "VM '$vmId' is already stopped/deallocated. Skipping."
            $skipped++
            continue
        }

        Write-Host "Stopping (deallocating) VM: $vmId"
        Stop-VMAsync -VMResourceId $vmId -Token $token
        Write-Host "Stop initiated for: $vmId"
        $stopped++

    } catch {
        Write-Host "Failed to stop VM '$vmId'. Error: $($_.Exception.Message)"
        $failed++
    }
}

Write-Host "=== Summary ==="
Write-Host "VMs stopped: $stopped"
Write-Host "VMs skipped (already stopped): $skipped"
Write-Host "VMs failed: $failed"
Write-Host "Post-maintenance VM stop function completed."
