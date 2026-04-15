# Application Gateway Troubleshooting Dashboard

An Azure Workbook that queries the `AzureDiagnostics` table (category `ApplicationGatewayAccessLog`) to help investigate and troubleshoot Application Gateway issues.

## Features

### Filters
All visualizations respect the following parameter filters:

- **Time Range** — adjustable from 5 minutes to 30 days, with custom range support
- **Subscription** — multi-select across subscriptions
- **Application Gateway** — filter to one or more gateways
- **Rule Name** — narrow down by routing rule
- **Listener Name** — filter by specific listener
- **Backend Pool** — isolate a backend pool
- **Error Info** — filter by Application Gateway error category
- **HTTP Status** — filter by response status code

### Tabs

| Tab | What it shows |
|-----|---------------|
| **Overview** | Key metrics tiles (total requests, failures, latency, unique clients, bytes), request volume by status category over time, and per-gateway error rates |
| **Error Analysis** | Errors by category (pie chart), by HTTP status (bar chart), top errors by rule/listener (table), and error trend over time |
| **Backend Health** | Backend pool performance (latency, error count), per-server breakdown, and server latency over time |
| **Request Details** | Top requested URIs, top client IPs, and a detailed request log (latest 250 entries) with color-coded status codes |
| **Timeline** | Request volume, latency percentiles (P50/P95/P99), throughput (MB sent/received), and requests by listener over time |

## Prerequisites

- Application Gateway diagnostic settings must be configured to send **Access Logs** to a Log Analytics workspace
- The logs should be in **Azure Diagnostics** mode (the `AzureDiagnostics` table)
- Reader access to the Log Analytics workspace

## Deployment

### Azure Portal (manual)

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of `appgw-troubleshooting-workbook.json`
5. Click **Apply**, then **Save**

## Data Source

This workbook queries:

```kql
AzureDiagnostics
| where Category == 'ApplicationGatewayAccessLog'
```

Key columns used: `clientIP_s`, `httpMethod_s`, `requestUri_s`, `httpStatus_d`, `serverStatus_d`, `timeTaken_d`, `serverResponseLatency_d`, `ruleName_s`, `listenerName_s`, `backendPoolName_s`, `backendSettingName_s`, `serverRouted_s`, `errorInfo_s`, `sslEnabled_s`, `hostname_s`, `userAgent_s`, `sentBytes_d`, `receivedBytes_d`.

## Files

| File | Description |
|------|-------------|
| `appgw-troubleshooting-workbook.json` | The Azure Workbook definition |
| `logsample.csv` | Sample log extract from `AzureDiagnostics` for reference |
