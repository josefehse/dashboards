# Azure Scheduled Events infrastructure

This folder contains two independent infrastructure packages:

- [Data collection rule](#data-collection-rule) for sending local Windows events to Log Analytics.
- [Event Grid custom topic](event-grid-topic.README.md) for triggering Logic Apps or Azure Functions directly from `SchServiceEventGrid.ps1`.

## Data collection rule

These templates create an Azure Monitor data collection rule (DCR) that sends only Windows Application log events with source `AzureScheduledEvents` and event ID `0` or `1234` to the Log Analytics `Event` table.

Both implementations use this XPath query:

```text
Application!*[System[Provider[@Name='AzureScheduledEvents'] and (EventID=0 or EventID=1234)]]
```

See [Windows Application Event Reference](../docs/event-log-events.md) for the event definitions and payload formats.

## Prerequisites

- An existing Log Analytics workspace.
- A resource group in which to create the DCR.
- The `Microsoft.Insights` resource provider registered in the subscription.
- Azure Monitor Agent installed on each target Windows VM, VM scale set, or Azure Arc-enabled server.
- A DCR association between this rule and each target resource.

The DCR location must match the Log Analytics workspace region. The templates do not create the workspace, Azure Monitor Agent, a data collection endpoint, or DCR associations.

## Bicep

The Bicep template is in [`bicep/main.bicep`](bicep/main.bicep).

```powershell
az deployment group create `
  --resource-group <dcr-resource-group> `
  --template-file .\bicep\main.bicep `
  --parameters `
    dataCollectionRuleName=<dcr-name> `
    location=<workspace-region> `
    logAnalyticsWorkspaceResourceId=<workspace-resource-id>
```

Inputs:

| Name | Required | Description |
| --- | --- | --- |
| `dataCollectionRuleName` | Yes | Name of the DCR. |
| `location` | Yes | Azure region matching the Log Analytics workspace region. |
| `logAnalyticsWorkspaceResourceId` | Yes | Full resource ID of the existing workspace. |
| `tags` | No | Tags applied to the DCR. |

Outputs include the DCR resource ID, name, and immutable ID.

## Terraform

The reusable Terraform child module is in [`terraform`](terraform). Configure the AzureRM provider in the calling root module.

```hcl
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.6"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

module "azure_scheduled_events_dcr" {
  source = "./terraform"

  data_collection_rule_name          = "dcr-azure-scheduled-events"
  resource_group_name                = "<dcr-resource-group>"
  location                           = "<workspace-region>"
  log_analytics_workspace_resource_id = "<workspace-resource-id>"
  tags = {
    workload = "azure-maintenance"
  }
}
```

Run the module from the calling root configuration:

```powershell
terraform init
terraform validate
terraform plan
```

The module outputs the DCR resource ID, name, and immutable ID.

## Associate the rule

Creating a DCR does not activate collection. Install Azure Monitor Agent and create a DCR association for every target VM, VM scale set, or Azure Arc-enabled server. Keeping associations outside this module allows one rule to be reused across deployment scopes and resource types.

## Verify ingestion

After the agent and association are active, run:

```kusto
Event
| where EventLog == "Application"
| where Source == "AzureScheduledEvents"
| where EventID in (0, 1234)
| project TimeGenerated, Computer, EventID, EventLevelName, RenderedDescription
| order by TimeGenerated desc
```

Records can take several minutes to appear after the agent and association become active.
