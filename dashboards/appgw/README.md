# Application Gateway Configuration Dashboard

This Azure Workbook provides a comprehensive view of all Application Gateways in your Azure subscription.

## Features

- **Overview Tab**: Lists all Application Gateways with key metrics
- **Basic Configuration**: SKU, capacity, autoscaling, WAF settings
- **Backend Pools**: View all backend address pools and their targets
- **Health Probes**: Configuration of health probes
- **Listeners**: HTTP/HTTPS listeners with SSL certificates
- **Routing Rules**: Request routing rules with priorities
- **Backend Health**: Real-time health status metrics

## Deployment

### Option 1: PowerShell Script
```powershell
.\Deploy-AppGatewayWorkbook.ps1 -ResourceGroupName "monitoring-rg" -Location "eastus"
```

### Option 2: Manual Deployment
1. Go to Azure Portal > Monitor > Workbooks
2. Click "New"
3. Click "</> Advanced Editor"
4. Paste the content of `application-gateway-workbook.json`
5. Click "Apply"
6. Save the workbook

## Usage

1. Open the workbook in Azure Portal
2. Select your subscription(s) and optionally filter by resource group
3. Click on any Application Gateway in the overview table
4. Navigate through tabs to view detailed configuration

## Requirements

- Azure subscription with Application Gateway resources
- Reader access to Application Gateway resources
- Azure Monitor metrics access
