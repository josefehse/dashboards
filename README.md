# Azure Monitoring Dashboards

A collection of Azure Workbooks and Grafana dashboards for monitoring, auditing, and managing Azure infrastructure. Each dashboard provides deep visibility into specific Azure services to help with day-to-day operations, security posture, and migration planning.

## Dashboards

| Dashboard | Type | Folder | Description |
|-----------|------|--------|-------------|
| [ADE to Host Encryption Migration](#ade-to-host-encryption-migration) | Azure Workbook | `ademigration/` | Track VM encryption status and plan migration from Azure Disk Encryption to Encryption at Host |
| [Application Gateway Configuration](#application-gateway-configuration) | Azure Workbook | `appgw/` | View and audit Application Gateway settings, backend health, listeners, and routing rules |
| [Application Gateway Troubleshooting](#application-gateway-troubleshooting) | Azure Workbook | `appgwtroubleshooting/` | Investigate access log errors, latency, and backend issues with drill-down filters |
| [Entra ID Sign-in Analysis](#entra-id-sign-in-analysis) | Azure Workbook / Grafana | `entraID/` | Analyze sign-in patterns and track ADAL-to-MSAL migration progress |
| [VNet Flow Log Analysis](#vnet-flow-log-analysis) | Azure Workbook | `flowlog/` | Analyze virtual network traffic flows, sources, destinations, and bandwidth usage |
| [Load Balancer Configuration](#load-balancer-configuration) | Azure Workbook | `loadbalancers/` | Inventory all load balancers with backend pools, health probes, and rules |
| [Virtual Networks Summary](#virtual-networks-summary) | Azure Workbook | `vnetsummary/` | List VNets and subnets with associated NSGs and route tables |

---

### ADE to Host Encryption Migration

**Folder:** `ademigration/`

Tracks VM encryption status across your subscriptions and helps plan the migration from the deprecated Azure Disk Encryption (ADE) to Encryption at Host. Identifies VMs still using ADE and highlights disks with residual ADE flags that may block migration.

- **File:** `ade-to-host-encryption-workbook.json`

### Application Gateway Configuration

**Folder:** `appgw/`

Provides a comprehensive view of all Application Gateways in your subscriptions, including SKU and capacity details, WAF settings, backend pools, health probes, listeners, SSL certificates, routing rules, and real-time backend health metrics.

- **Files:** `application-gateway-workbook.json`, `Deploy-AppGatewayWorkbook.ps1`
- **Deployment script included** — see the [appgw README](appgw/README.md) for details.

### Application Gateway Troubleshooting

**Folder:** `appgwtroubleshooting/`

Queries Application Gateway access logs (`AzureDiagnostics` / `ApplicationGatewayAccessLog`) to help investigate errors, latency spikes, and backend failures. Provides filters for subscription, gateway, rule, listener, backend pool, error category, and HTTP status. Includes five tabs: Overview, Error Analysis, Backend Health, Request Details, and Timeline.

- **Files:** `appgw-troubleshooting-workbook.json`, `logsample.csv`
- See the [appgwtroubleshooting README](appgwtroubleshooting/README.md) for details.

### Entra ID Sign-in Analysis

**Folder:** `entraID/`

Analyzes Entra ID (Azure AD) sign-in patterns with a focus on identifying applications still using the deprecated ADAL library. Tracks sign-in success/failure rates and guides migration from ADAL to MSAL.

- **Files:** `entraidWB.json` (Azure Workbook), `entraidWB-grafana.json` (Grafana dashboard)

### VNet Flow Log Analysis

**Folder:** `flowlog/`

Analyzes virtual network flow log data to provide visibility into network traffic patterns, including source/destination analysis, internal vs. external flows, and bytes sent/received per network interface.

- **File:** `vnetflowlog4.json`

### Load Balancer Configuration

**Folder:** `loadbalancers/`

Displays all load balancers across your subscriptions with details on SKU, scaling configuration, backend pool membership, health probe status, and load balancing rules.

- **Files:** `loadbalancers.json`, `loadbalancersDashboard.zip`

### Virtual Networks Summary

**Folder:** `vnetsummary/`

Lists all virtual networks and their subnets with address space details, linked NSGs, and user-defined route tables — useful for quick auditing of network topology and security configuration.

- **File:** `vnetsSummary.json`

---

## Deployment

Most dashboards are **Azure Workbooks** and can be deployed via the Azure Portal:

1. Go to **Azure Portal → Monitor → Workbooks**
2. Click **New**
3. Open the **Advanced Editor** (`</>`)
4. Paste the contents of the relevant `.json` file
5. Click **Apply**, then **Save**

For the Application Gateway workbook, a PowerShell deployment script is also available — see the [appgw README](appgw/README.md).

For the **Grafana** dashboard (`entraidWB-grafana.json`), import it through your Grafana instance's dashboard import feature.

## Prerequisites

- An Azure subscription with the relevant resources deployed
- **Reader** access to the target resources
- **Azure Monitor** metrics access
- For Entra ID dashboards: access to Azure AD sign-in logs
- For Grafana dashboards: a Grafana instance with an Azure Monitor data source configured
