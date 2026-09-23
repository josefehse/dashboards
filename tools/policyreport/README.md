# Policy Report

This folder contains a PowerShell script that gathers Azure Policy and initiative assignments from the current Azure context, exports a JSON report, and generates a simple HTML summary.

## Usage

From Azure Cloud Shell or a PowerShell session that is already authenticated to Azure:

```powershell
./Generate-PolicyAssignmentReport.ps1
```

Optional parameters:

```powershell
./Generate-PolicyAssignmentReport.ps1 -SubscriptionId <subscription-id>
```

The script writes:
- policiesreport.json
- policiesreport.html
