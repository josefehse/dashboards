# Entra ID Sign-in Analysis

Azure Workbook and Grafana dashboard to analyze Entra ID (Azure AD) sign-in patterns with a focus on identifying applications still using the deprecated ADAL library.

## Features

- Analyze sign-in success/failure rates
- Identify applications using deprecated ADAL library
- Track ADAL-to-MSAL migration progress
- Visualize sign-in patterns over time

## Files

| File | Description |
|------|-------------|
| `entraidWB.json` | Azure Workbook definition |
| `entraidWB-grafana.json` | Grafana dashboard definition |

## Deployment

### Azure Workbook

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of `entraidWB.json`
5. Click **Apply**, then **Save**

### Grafana Dashboard

1. Open your Grafana instance
2. Go to **Dashboards → Import**
3. Upload or paste the contents of `entraidWB-grafana.json`
4. Select your Azure Monitor data source
5. Click **Import**

## Prerequisites

- Access to Azure AD sign-in logs
- For Azure Workbook: Azure Monitor access
- For Grafana: Grafana instance with Azure Monitor data source configured
