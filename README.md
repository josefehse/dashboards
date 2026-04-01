# Azure Monitoring Dashboards & Tools

A collection of Azure Workbooks, Grafana dashboards, and operational tools for monitoring, auditing, and managing Azure infrastructure.

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

## Tools

| Tool | Folder | Description |
|------|--------|-------------|
| [Table Retention Manager](#table-retention-manager) | `tools/law-retention/` | Bulk-manage Interactive and Total retention settings for Log Analytics workspace tables |
| [Granular RBAC Manager](#granular-rbac-manager) | `tools/granularRBAC/` | Grant, revoke, and audit row-level access control (ABAC) on Log Analytics tables |

### Table Retention Manager

**Folder:** `tools/law-retention/`

PowerShell script to list, report, and update retention settings across all tables in a Log Analytics workspace. Supports default retention for all tables with optional per-table overrides via CSV. Includes confirmation prompts and exports a summary report.

- **Files:** `Set-TableRetention.ps1`, `sample-overrides.csv`
- See the [law-retention README](tools/law-retention/README.md) for usage examples.

### Granular RBAC Manager

**Folder:** `tools/granularRBAC/`

PowerShell scripts to automate row-level access control for Azure Monitor Log Analytics using [Granular RBAC (ABAC conditions)](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-log-analytics). Grant or revoke access for Entra ID groups to specific tables filtered by column values, and audit existing assignments.

- **Scripts:**
  - `Grant-GranularRBAC.ps1` — Create role assignments with ABAC conditions
  - `Revoke-GranularRBAC.ps1` — Remove granular RBAC assignments
  - `Show-GranularRBAC.ps1` — Audit all granular RBAC assignments on a workspace
- See the [granularRBAC README](tools/granularRBAC/README.md) for usage examples.

---

## Disclaimer

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Always test in a non-production environment first. The authors are not responsible for any unintended changes, data exposure, or service disruptions resulting from the use of these tools. Use at your own risk.
