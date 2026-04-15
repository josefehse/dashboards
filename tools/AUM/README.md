# Azure Update Manager Pre-Maintenance Functions

Azure Functions and Automation Account runbooks that respond to Azure Update Manager pre-maintenance events via Event Grid. Automate pre-maintenance tasks to protect your VMs before scheduled updates.

## Functions

| Function | Description |
|----------|-------------|
| `snapshot-vms` | Creates disk snapshots of all VMs in the maintenance scope before patching |
| `start-vms` | Starts deallocated VMs so they receive scheduled patches |
| `stop-vms` | Stops VMs after maintenance completes |

## Structure

```
AUM/
├── Function/                    # Azure Functions (PowerShell)
│   ├── host.json
│   ├── local.settings.json
│   ├── profile.ps1
│   ├── requirements.psd1
│   ├── Modules/
│   │   └── AUM-Helpers/         # Shared helper module
│   │       ├── AUM-Helpers.psd1
│   │       └── AUM-Helpers.psm1
│   ├── snapshot-vms/
│   │   ├── function.json
│   │   └── run.ps1
│   ├── start-vms/
│   │   ├── function.json
│   │   └── run.ps1
│   └── stop-vms/
│       ├── function.json
│       └── run.ps1
└── automationAccount/           # Azure Automation runbooks
    ├── snapshot-vms-rest.ps1
    ├── start-vms-rest.ps1
    ├── stop-vms-rest.ps1
    └── webhookmsample.json
```

## How It Works

1. **Azure Update Manager** schedules a maintenance window for your VMs
2. **Event Grid** triggers a `Microsoft.Maintenance.PreMaintenanceEvent` before maintenance starts
3. **Azure Function** receives the event and:
   - Extracts VM resource IDs from the maintenance scope
   - Performs the pre-maintenance action (snapshot, start, or stop)
   - Uses managed identity for authentication

## Configuration

### Environment Variables (Function App)

| Variable | Description |
|----------|-------------|
| `SNAPSHOT_RESOURCE_GROUP` | Resource group for snapshots (defaults to VM's RG) |
| `SNAPSHOT_NAME_PREFIX` | Prefix for snapshot names (default: `premaint`) |

### Prerequisites

- Azure Function App with PowerShell runtime
- System-assigned managed identity with:
  - **Reader** on the maintenance configuration scope
  - **VM Contributor** on VMs (for start/stop)
  - **Disk Snapshot Contributor** on target resource group (for snapshots)
- Event Grid subscription pointing to the Function App

## Deployment

### Azure Functions

1. Create a PowerShell Function App in Azure
2. Deploy the `Function/` folder contents
3. Enable system-assigned managed identity
4. Assign required RBAC roles
5. Create Event Grid subscription for maintenance events

### Azure Automation

1. Import the runbooks from `automationAccount/`
2. Configure the Automation Account's managed identity
3. Create Event Grid subscription with webhook trigger

## Local Development

```powershell
cd Function
func start
```

Requires [Azure Functions Core Tools](https://docs.microsoft.com/azure/azure-functions/functions-run-local).
