# 🔒 Azure Monitor Granular RBAC — Onboarding & Offboarding Scripts

Automate **row-level access control** for Azure Monitor Log Analytics using [Granular RBAC (ABAC conditions)](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-log-analytics). These PowerShell scripts let you grant or revoke access for Entra ID groups to specific Log Analytics tables, filtered by a column value — no portal clicking required.

---

## 📖 What is Granular RBAC?

Azure Monitor's Granular RBAC extends traditional role-based access control with **Attribute-Based Access Control (ABAC) conditions**. Instead of granting blanket read access to an entire workspace, you can restrict access to:

- A **specific table** (e.g., `CommonSecurityLog`)
- **Specific rows** within that table, filtered by a column value (e.g., `DeviceVendor = "Check Point"`)

This is the **"No access to data, except what is allowed"** strategy described in the [Microsoft documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-use-case).

### How it works under the hood

When you assign a role like **Log Analytics Data Reader** with an ABAC condition, Azure evaluates the condition on every data read. The condition is expressed as:

```
(
  !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})
)
OR
(
  @Resource[...tables:name] StringEquals 'TableName'
  AND
  @Resource[...tables/record:ColumnName] ForAnyOfAnyValues:StringLikeIgnoreCase {'Value1', 'Value2'}
)
```

This means: *"Allow data reads **only** when the table and column value match the condition."*

---

## 🗂️ Scripts

| Script | Purpose |
|--------|---------|
| [`Grant-GranularRBAC.ps1`](#grant-granularrbacps1) | Onboard groups — create role assignments with ABAC conditions |
| [`Revoke-GranularRBAC.ps1`](#revoke-granularrbacps1) | Offboard groups — find and remove matching role assignments |
| [`Show-GranularRBAC.ps1`](#show-granularrbacps1) | Audit — display all granular RBAC assignments on a workspace |

---

## ⚙️ Prerequisites

| Requirement | Details |
|-------------|---------|
| **PowerShell** | 7.x recommended; 5.1 supported |
| **Az Modules** | `Az.Resources`, `Az.OperationalInsights` |
| **Azure Login** | Run `Connect-AzAccount` before executing scripts |
| **Permissions** | [Role Based Access Control Administrator](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/#role-based-access-control-administrator) or [User Access Administrator](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/privileged#user-access-administrator) on the workspace scope |

Install the required modules if you don't have them:

```powershell
Install-Module Az.Resources -Scope CurrentUser
Install-Module Az.OperationalInsights -Scope CurrentUser
```

---

## 🚀 Grant-GranularRBAC.ps1

Creates role assignments with ABAC conditions for one or more Entra ID groups, restricting access to rows in a Log Analytics table that match specific column values.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `WorkspaceResourceId` | ✅ | — | Full Azure resource ID of the Log Analytics workspace |
| `GroupNames` | ✅ | — | One or more Entra ID group display names |
| `TableName` | ✅ | — | Log Analytics table name (e.g., `CommonSecurityLog`) |
| `ColumnName` | ✅ | — | Column to filter on (e.g., `DeviceVendor`) |
| `ColumnValues` | ✅ | — | Allowed value(s) for the column |
| `RoleDefinitionName` | ❌ | `Log Analytics Data Reader` | Built-in or custom role to assign |
| `-WhatIf` | ❌ | — | Preview changes without applying |

### What it does

1. **Resolves group names** to Object IDs (errors if name not found or duplicates exist)
2. **Validates** the workspace exists and you're authenticated
3. **Checks for conflicting role assignments** — warns if the group already has broad roles (e.g., `Reader`, `Contributor`) at the workspace or parent scope that would override the restriction
4. **Builds the ABAC condition** using the restrictive strategy
5. **Creates role assignments** with the condition for each group
6. **Reports a summary** of all actions taken

### Example

```powershell
.\Grant-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/my-rg/providers/Microsoft.OperationalInsights/workspaces/my-workspace" `
    -GroupNames "FirewallAdmins", "NetworkOps" `
    -TableName "CommonSecurityLog" `
    -ColumnName "DeviceVendor" `
    -ColumnValues "Check Point", "SonicWall"
```

#### Dry run

```powershell
.\Grant-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
    -GroupNames "FirewallAdmins" `
    -TableName "CommonSecurityLog" `
    -ColumnName "DeviceVendor" `
    -ColumnValues "Check Point" `
    -WhatIf
```

---

## 🗑️ Revoke-GranularRBAC.ps1

Finds and removes granular RBAC role assignments that match the specified groups and table name.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `WorkspaceResourceId` | ✅ | — | Full Azure resource ID of the Log Analytics workspace |
| `GroupNames` | ✅ | — | One or more Entra ID group display names |
| `TableName` | ✅ | — | Table name to match in the ABAC condition |
| `RoleDefinitionName` | ❌ | `Log Analytics Data Reader` | Role to filter on |
| `-Force` | ❌ | — | Skip confirmation prompts |
| `-WhatIf` | ❌ | — | Preview changes without applying |

### What it does

1. **Resolves group names** to Object IDs (errors if name not found or duplicates exist)
2. **Finds role assignments** for each group at the workspace scope that have an ABAC condition referencing the specified table
3. **Prompts for confirmation** before removing (unless `-Force` is used)
4. **Removes the assignments** and reports results

### Example

```powershell
# Interactive (prompts for confirmation)
.\Revoke-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
    -GroupNames "FirewallAdmins" `
    -TableName "CommonSecurityLog"

# Non-interactive
.\Revoke-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
    -GroupNames "FirewallAdmins" `
    -TableName "CommonSecurityLog" `
    -Force
```

---

## 🔎 Show-GranularRBAC.ps1

Retrieves and displays all role assignments with ABAC conditions on a workspace. Parses conditions to show table names, column names, and allowed values in a readable format.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `WorkspaceResourceId` | ✅ | — | Full Azure resource ID of the Log Analytics workspace |
| `GroupObjectId` | ❌ | — | Filter results to a specific Entra ID group |
| `TableName` | ❌ | — | Filter results to assignments referencing a specific table |
| `IncludeBroadRoles` | ❌ | — | Also show assignments without ABAC conditions |
| `Detailed` | ❌ | — | Display full ABAC condition text |

### What it does

1. **Retrieves all role assignments** at the workspace scope
2. **Parses ABAC conditions** to extract table, column, and value information
3. **Displays a summary** of granular vs. broad access assignments
4. **Lists each assignment** with principal, role, and access scope details
5. **Returns structured objects** for pipeline usage (e.g., export to CSV)

### Example

```powershell
# Show all granular RBAC assignments
.\Show-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/my-rg/providers/Microsoft.OperationalInsights/workspaces/my-workspace"

# Filter by table and show full condition text
.\Show-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
    -TableName "CommonSecurityLog" `
    -Detailed

# Include broad roles and export to CSV
.\Show-GranularRBAC.ps1 `
    -WorkspaceResourceId "/subscriptions/.../workspaces/my-workspace" `
    -IncludeBroadRoles | Export-Csv -Path "rbac-audit.csv" -NoTypeInformation
```

---

## ⚠️ Important Notes

### User Permissions

Users with granular RBAC need **two** role assignments to access the workspace:

| Role | Purpose | Has Data Access? |
|------|---------|------------------|
| **Reader** | See workspace in Azure portal | ❌ No |
| **Log Analytics Data Reader** (with ABAC) | Query restricted table/rows | ✅ Restricted only |

**Roles to avoid** (these grant broad data access and override granular RBAC):
- `Log Analytics Reader`
- `Monitoring Reader`
- `Contributor` / `Owner`

### Other Considerations

- **Additive role assignments** — If a group already has a broad role like `Log Analytics Reader` without conditions at the same or higher scope, the granular restriction will **not** be effective. The grant script warns about this, but does not remove conflicting assignments automatically.
- **Propagation delay** — Changes may take **up to 15 minutes** to take effect.
- **Case sensitivity** — Table names and column values in conditions are case-sensitive. The scripts use `StringLikeIgnoreCase` for column values to reduce errors, but table names must match exactly.
- **Condition limits** — The Azure portal visual editor supports up to 5 expressions. These scripts build conditions programmatically and are not limited by the portal UI.

---

## 🔍 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| User still sees all data | Broad role exists at a higher scope | Check and remove conflicting role assignments |
| User sees no data | Table name or column name is misspelled | Verify exact table/column names in Log Analytics |
| `400 Bad Request` for queries | Invalid ABAC condition (e.g., column doesn't exist) | Review and correct the condition; see [ABAC troubleshooting](https://learn.microsoft.com/en-us/azure/role-based-access-control/conditions-troubleshoot) |
| Changes not visible yet | Normal propagation delay | Wait up to 15 minutes |

You can audit whether conditions are being applied by querying the `LAQueryLogs` table and checking the `ConditionalDataAccess` column. See [LAQueryLogs reference](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/laquerylogs).

---

## 📚 References

- [Granular RBAC in Azure Monitor — Concepts](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-log-analytics)
- [Granular RBAC in Azure Monitor — Use Case Walkthrough](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-use-case)
- [Add or Edit ABAC Conditions via REST](https://learn.microsoft.com/en-us/azure/role-based-access-control/conditions-role-assignments-rest)
- [Troubleshoot Azure ABAC Conditions](https://learn.microsoft.com/en-us/azure/role-based-access-control/conditions-troubleshoot)
- [Azure Built-in Roles — Log Analytics Data Reader](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/analytics#log-analytics-reader)
- [LAQueryLogs Table Reference](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/laquerylogs)

---

## 📄 License

MIT — use, modify, and distribute freely.

---

## ⚖️ Disclaimer

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

These scripts modify Azure role assignments. Always test in a non-production environment first. The authors are not responsible for any unintended access grants, data exposure, or service disruptions resulting from the use of these scripts. Use at your own risk.
