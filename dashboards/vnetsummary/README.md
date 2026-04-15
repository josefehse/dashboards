# Virtual Networks Summary Workbook

Azure Workbook to list all virtual networks and their subnets with security and routing configuration details.

## Features

- List all VNets with address space details
- Subnet inventory with CIDR ranges
- Associated Network Security Groups (NSGs)
- User-defined route tables (UDRs)
- Quick auditing of network topology and security configuration

## Files

| File | Description |
|------|-------------|
| `vnetsSummary.json` | Azure Workbook definition |

## Deployment

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of `vnetsSummary.json`
5. Click **Apply**, then **Save**

## Prerequisites

- Azure subscription with virtual networks deployed
- **Reader** access to the target subscriptions
