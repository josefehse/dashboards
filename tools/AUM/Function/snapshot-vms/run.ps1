# Input bindings are passed in via param block.
param($eventGridEvent, $TriggerMetadata)

Write-Host "Pre-maintenance disk snapshot function triggered."
Write-Host "Event Type: $($eventGridEvent.eventType)"
Write-Host "Event Subject: $($eventGridEvent.subject)"

# --- Configuration from app settings ---
$SnapshotResourceGroup = $env:SNAPSHOT_RESOURCE_GROUP  # If not set, snapshots go to same RG as VM
$SnapshotNamePrefix = $env:SNAPSHOT_NAME_PREFIX
if (-not $SnapshotNamePrefix) { $SnapshotNamePrefix = "premaint" }

# --- Validate event type ---
if ($eventGridEvent.eventType -ne "Microsoft.Maintenance.PreMaintenanceEvent") {
    Write-Host "Skipping eventType '$($eventGridEvent.eventType)' - this function handles PreMaintenanceEvent only."
    return
}

# --- Get token and discover VMs ---
$token = Get-ManagedIdentityToken -Resource "https://management.azure.com/"

$vmResourceIds = Get-MaintenanceEventVMs -Event $eventGridEvent -Token $token

if ($vmResourceIds.Count -eq 0) {
    Write-Host "No VMs found to snapshot."
    return
}

Write-Host "VMs to snapshot (count=$($vmResourceIds.Count)):"
$vmResourceIds | ForEach-Object { Write-Host $_ }

# --- Create snapshots for each VM's disks ---
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapshotsCreated = 0
$snapshotsFailed = 0

foreach ($vmId in $vmResourceIds) {
    try {
        Write-Host "--- Processing VM: $vmId ---"

        # Parse VM resource ID
        $vmInfo = ConvertFrom-VMResourceId -ResourceId $vmId
        if (-not $vmInfo) {
            Write-Host "Could not parse VM resource ID: $vmId"
            continue
        }

        # Get VM details to find attached disks
        $vm = Get-VMDetails -VMResourceId $vmId -Token $token

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

        Write-Host "Found $($disksToSnapshot.Count) disk(s) to snapshot for VM '$($vmInfo.Name)'."

        # Determine target resource group for snapshots
        $targetRg = if ($SnapshotResourceGroup) { $SnapshotResourceGroup } else { $vmInfo.ResourceGroup }

        # Create snapshot for each disk
        foreach ($disk in $disksToSnapshot) {
            $snapshotName = "$SnapshotNamePrefix-$($vmInfo.Name)-$($disk.DiskType)-$timestamp"
            
            # Ensure snapshot name is valid (max 80 chars, alphanumeric, underscores, hyphens, periods)
            $snapshotName = $snapshotName -replace '[^a-zA-Z0-9_\-\.]', '-'
            if ($snapshotName.Length -gt 80) {
                $snapshotName = $snapshotName.Substring(0, 80)
            }

            Write-Host "Creating snapshot '$snapshotName' for disk '$($disk.DiskName)'..."

            $snapshotUri = "https://management.azure.com/subscriptions/$($vmInfo.SubscriptionId)/resourceGroups/$targetRg/providers/Microsoft.Compute/snapshots/$snapshotName`?api-version=2024-03-02"

            $snapshotBody = @{
                location   = $vmLocation
                tags       = @{
                    "Maintenance" = "Patching"
                    "SourceVM"    = $vmInfo.Name
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
                Invoke-AzureRestApi -Method PUT -Uri $snapshotUri -Token $token -Body $snapshotBody | Out-Null
                Write-Host "Snapshot creation initiated: $snapshotName"
                $snapshotsCreated++
            } catch {
                Write-Host "Failed to create snapshot for disk '$($disk.DiskName)': $($_.Exception.Message)"
                $snapshotsFailed++
            }
        }

    } catch {
        Write-Host "Failed to process VM '$vmId': $($_.Exception.Message)"
        $snapshotsFailed++
    }
}

Write-Host "=== Summary ==="
Write-Host "Total VMs processed: $($vmResourceIds.Count)"
Write-Host "Snapshots created: $snapshotsCreated"
Write-Host "Snapshots failed: $snapshotsFailed"
Write-Host "Pre-maintenance disk snapshot function completed."
