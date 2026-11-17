# Azure Scheduled Events Service

This project enables Azure Windows virtual machines to subscribe to [Scheduled Events](https://learn.microsoft.com/azure/virtual-machines/windows/scheduled-events). The PowerShell service polls Azure Instance Metadata Service, writes service and maintenance records to the Windows Application event log, and approves newly detected scheduled events.

## Setup

1. Place `SchService.ps1` on the Azure Windows virtual machine.
2. Open an elevated PowerShell session and install the service:

   ```powershell
   .\SchService.ps1 -Setup
   ```

3. Start the service:

   ```powershell
   .\SchService.ps1 -Start
   ```

4. Confirm that it is running:

   ```powershell
   .\SchService.ps1 -Status
   ```

The service polls every 10 seconds. Scheduled-event types such as `Freeze`, `Reboot`, `Redeploy`, and `Preempt` are stored in JSON messages under source `AzureScheduledEvents`; they are not separate Windows Event IDs.

## Event reference and collection

- [Windows Application Event Reference](../docs/event-log-events.md) documents every explicit event emitted by the script and compiled service wrapper.
- [Data collection rule templates](../infra/README.md) provide equivalent Bicep and Terraform definitions that collect only source `AzureScheduledEvents` with event ID `0` or `1234` into Log Analytics.
- [Event Grid service alternative](Powershell/SchServiceEventGrid.README.md) documents the managed-identity publisher for triggering Logic Apps and Azure Functions.

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit the [Contributor License Agreement site](https://cla.microsoft.com).

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
