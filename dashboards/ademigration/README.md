# ADE to Host Encryption Migration Workbook

Azure Workbook to track VM encryption status across your subscriptions and help plan the migration from the deprecated Azure Disk Encryption (ADE) to Encryption at Host.

## Features

- Identifies VMs still using Azure Disk Encryption (ADE)
- Highlights disks with residual ADE flags that may block migration
- Tracks migration progress across subscriptions
- Helps prioritize VMs for encryption migration

## Files

| File | Description |
|------|-------------|
| `ade-to-host-encryption-workbook.json` | Azure Workbook definition |

## Deployment

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of `ade-to-host-encryption-workbook.json`
5. Click **Apply**, then **Save**

## Prerequisites

- Azure subscription with VMs deployed
- **Reader** access to the target subscriptions
