# Load Balancer Configuration Workbook

Azure Workbook to display all load balancers across your subscriptions with detailed configuration information.

## Features

- Inventory all Azure Load Balancers (Standard and Basic SKUs)
- View SKU and scaling configuration
- Backend pool membership details
- Health probe status and configuration
- Load balancing rules overview

## Files

| File | Description |
|------|-------------|
| `loadbalancers.json` | Azure Workbook definition |
| `loadbalancersDashboard.zip` | Exported dashboard package |

## Deployment

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of `loadbalancers.json`
5. Click **Apply**, then **Save**

## Prerequisites

- Azure subscription with Load Balancers deployed
- **Reader** access to the target subscriptions
