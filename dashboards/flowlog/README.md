# VNet Flow Log Analysis Workbook

Azure Workbook to analyze virtual network flow log data and provide visibility into network traffic patterns.

## Features

- Source and destination IP analysis
- Internal vs. external traffic flow visualization
- Bytes sent/received per network interface
- Traffic pattern identification

## Files

| File | Description |
|------|-------------|
| `vnetflowlog4.json` | Azure Workbook definition |

## Deployment

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of `vnetflowlog4.json`
5. Click **Apply**, then **Save**

## Prerequisites

- Azure subscription with VNet flow logs enabled
- Log Analytics workspace receiving flow log data
- **Reader** access to the workspace

## Related

For advanced flow log analysis using Azure Data Explorer, see the [flowsaver tool](../../tools/flowsaver/README.md).
