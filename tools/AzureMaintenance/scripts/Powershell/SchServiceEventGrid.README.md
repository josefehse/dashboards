# Azure Scheduled Events Event Grid service

`SchServiceEventGrid.ps1` is an alternative to `SchService.ps1`. It keeps the existing Windows Application event logging and scheduled-event approval behavior, and also publishes each newly detected scheduled event to an Azure Event Grid custom topic.

The service uses the VM's managed identity. No Event Grid access key, SAS token, client secret, or certificate is stored on the machine.

## Behavior

For each new scheduled event, the service:

1. Writes the scheduled-event JSON to the Windows Application log with source `AzureScheduledEvents` and event ID `1234`.
2. Publishes an Event Grid event using the VM's managed identity.
3. Retries transient publication failures up to three times.
4. Logs a final publication failure locally with event ID `1235`.
5. Approves the Azure scheduled event whether publication succeeded or failed.

Publishing is best effort. Event Grid can deliver an event more than once, so consumers should deduplicate on the Event Grid event `id`, which is the Azure Scheduled Events `EventId`.

Do not run `SchService.ps1` and `SchServiceEventGrid.ps1` simultaneously on the same VM. Both instances would observe and attempt to approve the same scheduled events.

## Requirements

- Windows PowerShell 5.1.
- An Azure VM with a system-assigned or user-assigned managed identity.
- An Azure Event Grid custom topic using the Event Grid input schema.
- The managed identity assigned the `EventGrid Data Sender` role on the topic.
- Outbound HTTPS access from the VM to the topic endpoint.

## Create the topic and grant access

Reusable [Bicep and Terraform templates](../../infra/event-grid-topic.README.md) are provided to create the custom topic and optionally grant the managed identity `EventGrid Data Sender` at topic scope.

The following manual example uses the VM's system-assigned identity:

```powershell
$subscriptionId = '<subscription-id>'
$topicResourceGroup = '<topic-resource-group>'
$topicName = '<globally-unique-topic-name>'
$location = '<azure-region>'
$vmResourceGroup = '<vm-resource-group>'
$vmName = '<vm-name>'

az account set --subscription $subscriptionId

az vm identity assign `
  --resource-group $vmResourceGroup `
  --name $vmName

az eventgrid topic create `
  --resource-group $topicResourceGroup `
  --name $topicName `
  --location $location `
  --input-schema eventgridschema `
  --disable-local-auth true

$principalId = az vm identity show `
  --resource-group $vmResourceGroup `
  --name $vmName `
  --query principalId `
  --output tsv

$topicId = az eventgrid topic show `
  --resource-group $topicResourceGroup `
  --name $topicName `
  --query id `
  --output tsv

az role assignment create `
  --assignee-object-id $principalId `
  --assignee-principal-type ServicePrincipal `
  --role 'EventGrid Data Sender' `
  --scope $topicId
```

Creating the role assignment requires `Microsoft.Authorization/roleAssignments/write`, typically through User Access Administrator or Owner.

## Configure the VM

Create `C:\ProgramData\AzureScheduledEvents\EventGridPublisher.json` from `EventGridPublisher.sample.json`:

```json
{
  "topicEndpoint": "https://my-topic.canadacentral-1.eventgrid.azure.net/api/events",
  "userAssignedIdentityClientId": null
}
```

Leave `userAssignedIdentityClientId` as `null` to use the VM's system-assigned identity. Set it to the client ID of a user-assigned identity attached to the VM when that identity should publish instead.

Do not put the system-assigned identity's principal/object ID in `userAssignedIdentityClientId`. Principal IDs are used for RBAC role assignments; this configuration field accepts only a user-assigned identity's client ID.

The endpoint must use HTTPS, end with `/api/events`, and contain no query string. The service appends the supported Event Grid publishing API version.

The service reads the configuration once during startup. Restart `SchServiceEventGrid` after changing the endpoint or managed identity client ID. If the configuration is missing or invalid, local logging and scheduled-event approval continue while Event Grid publishing remains disabled.

Restrict the configuration file to Administrators and SYSTEM:

```powershell
$configurationDirectory = 'C:\ProgramData\AzureScheduledEvents'
$configurationPath = Join-Path $configurationDirectory 'EventGridPublisher.json'

New-Item -ItemType Directory -Path $configurationDirectory -Force | Out-Null
Copy-Item .\EventGridPublisher.sample.json $configurationPath
notepad.exe $configurationPath

icacls.exe $configurationDirectory /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F'
```

## Install the alternative service

Remove or disable the original service before installing the alternative:

```powershell
.\SchService.ps1 -Stop
.\SchService.ps1 -Remove

.\SchServiceEventGrid.ps1 -Setup
.\SchServiceEventGrid.ps1 -Start
.\SchServiceEventGrid.ps1 -Status
```

The script basename becomes the Windows service name, so this alternative installs as `SchServiceEventGrid`.

If the configuration is missing or invalid, the service continues local logging and approval but disables Event Grid publishing for that service process. It writes event ID `1007` under source `SchServiceEventGrid`.

## Event Grid event schema

The topic receives Event Grid schema events with this shape:

```json
[
  {
    "id": "<scheduled-event-id>",
    "subject": "<vm-resource-id>/scheduledEvents/<scheduled-event-id>",
    "eventType": "AzureScheduledEvents.Detected",
    "eventTime": "2026-09-24T10:15:30.0000000Z",
    "data": {
      "publisherResourceId": "<vm-resource-id>",
      "documentIncarnation": "4",
      "scheduledEvent": {
        "EventId": "<scheduled-event-id>",
        "EventStatus": "Scheduled",
        "EventType": "Reboot",
        "ResourceType": "VirtualMachine",
        "Resources": [
          "vm-name"
        ],
        "NotBefore": "Thu, 24 Sep 2026 10:30:00 GMT"
      }
    },
    "dataVersion": "1.0"
  }
]
```

Consumers can filter subscriptions on event type `AzureScheduledEvents.Detected`, subject prefix, or fields inside `data.scheduledEvent`.

## Connect a Logic App or Azure Function

Create an Event Grid subscription on the custom topic and choose either:

- **Azure Function** endpoint for an Event Grid-triggered function.
- **Web Hook** endpoint for a Logic App using the Event Grid trigger.

Configure dead-lettering on the Event Grid subscription when failed downstream deliveries must be retained.

## Test

### Synthetic publisher test

Run the test helper from the Azure VM to validate the configuration file, managed identity token, `EventGrid Data Sender` role, outbound connectivity, and Event Grid topic without restarting the VM:

```powershell
.\Test-EventGridPublisher.ps1
```

To use a configuration file in another location:

```powershell
.\Test-EventGridPublisher.ps1 `
  -ConfigurationPath 'D:\Configuration\EventGridPublisher.json'
```

A successful request returns HTTP status `200` and publishes an event with type:

```text
AzureScheduledEvents.SyntheticTest
```

Use that event type as a temporary Event Grid subscription filter or inspect it in the receiving Logic App or Azure Function. The helper does not write event ID `1234` locally and does not approve or simulate an Azure Scheduled Event; it tests only the Event Grid publishing path.

### Scheduled-event integration test

1. Start the service and confirm `SchServiceEventGrid` reports `Running`.
2. Trigger **Restart** or **Redeploy** from the VM blade or Azure CLI.
3. Confirm event ID `1234` exists locally under source `AzureScheduledEvents`.
4. Confirm an `AzureScheduledEvents.Detected` event reached the topic subscriber.
5. Check event IDs `1007`, `1235`, and `1236` if publishing or approval did not complete.

The service publishes only newly detected IMDS scheduled events. Manually writing event ID `1234` to the Windows event log does not invoke Event Grid publication.
