# Windows Application Event Reference

`SchService.ps1` writes to the Windows **Application** event log. It uses two event sources:

- `SchService`, derived from the script file name without the `.ps1` extension. Renaming the script changes this source.
- `AzureScheduledEvents`, a fixed source used for scheduled-event processing.

The tables below document the events explicitly emitted by the PowerShell script and its compiled service wrapper.

## SchService events

### PowerShell service lifecycle

| Event ID | Level | Trigger | Message |
| --- | --- | --- | --- |
| 1001 | Information | Service Control Manager starts the script through `-SCMStart`. | `SchService.ps1 -SCMStart: Starting script '<script-full-path>' -Service` |
| 1002 | Information | An operator runs `SchService.ps1 -Start`. | `SchService.ps1 -Start: Starting service SchService` |
| 1003 | Information | Service Control Manager invokes `-SCMStop`. | `SchService.ps1 -SCMStop: Stopping script SchService.ps1 -Service` |
| 1004 | Information | An operator runs `SchService.ps1 -Stop`. | `SchService.ps1 -Stop: Stopping service SchService` |
| 1005 | Information | The background service process enters its main loop. | `SchService.ps1 -Service # Beginning background job` |
| 1006 | Information | The background service process exits, including after an exception handled by its outer `try` block. | `SchService -Service # Exiting` |

### Compiled service wrapper

The setup operation compiles a Windows service executable whose source is also `SchService`. Calls to the two-argument `EventLog.WriteEntry` overload create Information entries with event ID `0`. The explicit failure overload creates Error entries with event ID `0`.

| Event ID | Level | Trigger | Message |
| --- | --- | --- | --- |
| 0 | Information | The service class is constructed. | `SchService.exe SchService()` |
| 0 | Information | `OnStart` begins. | `SchService.exe OnStart() // Entry. Starting script '<installed-script-path>' -SCMStart` |
| 0 | Error | `OnStart` cannot start the PowerShell process successfully. | `SchService.exe OnStart() // Failed to start <installed-script-path>. <exception-message>` |
| 0 | Information | `OnStart` exits, whether startup succeeded or failed. | `SchService.exe OnStart() // Exit` |
| 0 | Information | `OnStop` begins. | `SchService.exe OnStop() // Entry` |
| 0 | Error | `OnStop` cannot stop the PowerShell process successfully. | `SchService.exe OnStop() // Failed to stop <installed-script-path>. <exception-message>` |
| 0 | Information | `OnStop` exits, whether shutdown succeeded or failed. | `SchService.exe OnStop() // Exit` |

The wrapper also sets `.NET ServiceBase.AutoLog` to `true`. The framework can therefore write additional start, stop, state-change, and command-failure entries to the Application log with source `SchService`. Their event IDs and localized messages are owned by the installed .NET Framework and Windows version, so they are not stable script-defined contracts.

## AzureScheduledEvents events

All entries from this source use the Information level.

| Event ID | Trigger | Message |
| --- | --- | --- |
| 0 | The timer first finds no existing entries for the `AzureScheduledEvents` source and registers the source. | `Script Started.` |
| 1234 | A scheduled event is returned by Azure Instance Metadata Service and its `EventId` is not found in an existing source message. | The complete scheduled-event object serialized as JSON. |
| 1234 | The service approves that newly detected scheduled event. | The approval request serialized as JSON. |

Event ID `1234` has two distinct payload shapes.

### Scheduled-event payload

The first ID `1234` entry is the event object returned in the Instance Metadata Service `Events` collection. Fields can include:

| Field | Meaning |
| --- | --- |
| `EventId` | Unique identifier used by the script for message-based deduplication and approval. |
| `EventType` | Maintenance action such as `Freeze`, `Reboot`, `Redeploy`, or `Preempt`. |
| `ResourceType` | Type of affected Azure resource. |
| `Resources` | Affected resource names. |
| `EventStatus` | Current scheduled-event status. |
| `NotBefore` | Earliest time at which the event can begin. |

Scheduled-event types are JSON values in `EventType`; they are not separate Windows Event IDs.

### Approval payload

The second ID `1234` entry is written immediately before the approval POST and has this shape:

```json
{
  "StartRequests": [
    {
      "EventId": "<event-id>"
    }
  ],
  "DocumentIncarnation": "<document-incarnation>"
}
```

An event log entry records the attempted approval, not confirmation that the subsequent HTTP POST succeeded.

## Deduplication behavior

Before logging a scheduled event, the script searches all Application log entries from `AzureScheduledEvents` for a message containing the event's `EventId`. If any message matches, the script skips both the event entry and approval. The search is a wildcard text match rather than a structured JSON comparison.

Creating an event source requires administrative permissions. The service attempts to create `AzureScheduledEvents` during a timer tick and reports a PowerShell security error if it cannot read or write the event log.

## Data collection filter

The Bicep and Terraform templates use this XPath query to collect only the explicit `AzureScheduledEvents` contract:

```text
Application!*[System[Provider[@Name='AzureScheduledEvents'] and (EventID=0 or EventID=1234)]]
```

This excludes all `SchService` lifecycle, wrapper, and framework-generated entries.

To validate the XPath on a Windows host that has the event source registered, remove the `Application!` prefix:

```powershell
Get-WinEvent -LogName Application `
  -FilterXPath "*[System[Provider[@Name='AzureScheduledEvents'] and (EventID=0 or EventID=1234)]]" `
  -MaxEvents 20
```

After the DCR is associated with a host running Azure Monitor Agent, verify ingestion in the Log Analytics `Event` table:

```kusto
Event
| where EventLog == "Application"
| where Source == "AzureScheduledEvents"
| where EventID in (0, 1234)
| project TimeGenerated, Computer, EventID, EventLevelName, RenderedDescription
| order by TimeGenerated desc
```

The two ID `1234` message shapes can be distinguished by their JSON properties.
