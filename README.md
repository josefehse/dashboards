# Azure Dashboards & Tools

A collection of Azure Workbooks, Grafana dashboards, and operational tools for monitoring, auditing, and managing Azure infrastructure.

## Repository Structure

```
├── dashboards/          # Azure Workbooks and Grafana dashboards
│   ├── ademigration/
│   ├── appgw/
│   ├── appgwtroubleshooting/
│   ├── entraID/
│   ├── flowlog/
│   ├── loadbalancers/
│   └── vnetsummary/
└── tools/               # Operational scripts and CLI tools
    ├── AUM/             # Azure Update Manager pre-maintenance functions
    ├── flowsaver/       # VNet flow log analysis with ADX
    ├── granularRBAC/    # Azure Monitor row-level access control
    ├── law-retention/   # Log Analytics table retention management
    └── netinspector/    # Network topology discovery and analysis
```

---

## Dashboards

| Dashboard | Type | Description |
|-----------|------|-------------|
| [ADE to Host Encryption Migration](dashboards/ademigration/README.md) | Azure Workbook | Track VM encryption status and plan migration from ADE to Encryption at Host |
| [Application Gateway Configuration](dashboards/appgw/README.md) | Azure Workbook | View and audit Application Gateway settings, backend health, and routing rules |
| [Application Gateway Troubleshooting](dashboards/appgwtroubleshooting/README.md) | Azure Workbook | Investigate access log errors, latency, and backend issues |
| [Entra ID Sign-in Analysis](dashboards/entraID/README.md) | Workbook / Grafana | Analyze sign-in patterns and track ADAL-to-MSAL migration |
| [VNet Flow Log Analysis](dashboards/flowlog/README.md) | Azure Workbook | Analyze virtual network traffic flows and bandwidth usage |
| [Load Balancer Configuration](dashboards/loadbalancers/README.md) | Azure Workbook | Inventory load balancers with backend pools and health probes |
| [Virtual Networks Summary](dashboards/vnetsummary/README.md) | Azure Workbook | List VNets and subnets with NSGs and route tables |

---

## Tools

| Tool | Type | Description |
|------|------|-------------|
| [Azure Update Manager Functions](tools/AUM/README.md) | Azure Functions | Pre-maintenance event handlers for VM snapshots, start, and stop |
| [Flow Log Analysis (flowsaver)](tools/flowsaver/README.md) | Python CLI | Parse and analyze VNet flow logs using Azure Data Explorer |
| [Granular RBAC](tools/granularRBAC/README.md) | PowerShell | Azure Monitor row-level access control with ABAC conditions |
| [Log Analytics Retention](tools/law-retention/README.md) | PowerShell | Bulk management of table retention settings |
| [Network Inspector](tools/netinspector/README.md) | Python CLI | Azure network topology discovery, analysis, and documentation |

## Prerequisites

### Dashboards

- An Azure subscription with the relevant resources deployed
- **Reader** access to the target resources
- **Azure Monitor** metrics access
- For Entra ID dashboards: access to Azure AD sign-in logs
- For Grafana dashboards: a Grafana instance with an Azure Monitor data source configured

### Tools

- **PowerShell tools** (`AUM`, `granularRBAC`, `law-retention`): PowerShell 7.x and Az modules
- **Python tools** (`flowsaver`, `netinspector`): Python 3.10+ and Azure CLI

---

## Disclaimer

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Always test in a non-production environment first. The authors are not responsible for any unintended changes, data exposure, or service disruptions resulting from the use of these tools. Use at your own risk.
