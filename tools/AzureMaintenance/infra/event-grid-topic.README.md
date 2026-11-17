# Event Grid custom topic infrastructure

These templates create the Event Grid custom topic used by `SchServiceEventGrid.ps1`.

Both implementations:

- Use the Event Grid event schema expected by the service.
- Disable local key and SAS authentication.
- Enable public network access to the topic endpoint.
- Optionally grant `EventGrid Data Sender` at topic scope to a managed identity.
- Output the topic endpoint and a service-compatible configuration object.

The optional publisher principal is the managed identity **object/principal ID**, not its client ID. Creating the role assignment requires `Microsoft.Authorization/roleAssignments/write`, typically through User Access Administrator or Owner.

## Bicep

The template is [`bicep/event-grid-topic.bicep`](bicep/event-grid-topic.bicep).

Obtain the VM's system-assigned identity principal ID and deploy:

```powershell
$vmPrincipalId = az vm identity show `
  --resource-group <vm-resource-group> `
  --name <vm-name> `
  --query principalId `
  --output tsv

$deployment = az deployment group create `
  --resource-group <topic-resource-group> `
  --template-file .\bicep\event-grid-topic.bicep `
  --parameters `
    topicName=<globally-unique-topic-name> `
    location=<azure-region> `
    publisherPrincipalId=$vmPrincipalId `
  | ConvertFrom-Json

$deployment.properties.outputs.publisherConfiguration.value |
  ConvertTo-Json |
  Set-Content .\EventGridPublisher.json
```

Inputs:

| Name | Required | Description |
| --- | --- | --- |
| `topicName` | Yes | Regionally unique Event Grid topic name, 3 to 50 characters. |
| `location` | No | Topic region; defaults to the deployment resource group's location. |
| `publisherPrincipalId` | No | Managed identity object/principal ID that receives `EventGrid Data Sender`. |
| `tags` | No | Tags applied to the topic. |

Outputs include `topicId`, `topicName`, `topicEndpoint`, and `publisherConfiguration`.

Validate before deployment:

```powershell
az bicep lint --file .\bicep\event-grid-topic.bicep

az deployment group validate `
  --resource-group <topic-resource-group> `
  --template-file .\bicep\event-grid-topic.bicep `
  --parameters topicName=<topic-name> publisherPrincipalId=<principal-id>
```

## Terraform

The reusable child module is [`terraform/event-grid-topic`](terraform/event-grid-topic).

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

module "scheduled_events_topic" {
  source = "./terraform/event-grid-topic"

  topic_name             = "<globally-unique-topic-name>"
  resource_group_name    = "<topic-resource-group>"
  location               = "<azure-region>"
  publisher_principal_id = "<managed-identity-principal-id>"

  tags = {
    workload = "azure-maintenance"
  }
}

output "event_grid_publisher_configuration" {
  value = module.scheduled_events_topic.publisher_configuration
}
```

Set `publisher_principal_id` to `null` to create only the topic and manage sender access separately.

Run:

```powershell
Push-Location .\terraform\event-grid-topic
terraform init
terraform validate
terraform plan
Pop-Location
```

## Configure the service

Copy the `publisherConfiguration` output to:

```text
C:\ProgramData\AzureScheduledEvents\EventGridPublisher.json
```

For a system-assigned identity, the output is:

```json
{
  "topicEndpoint": "https://<topic>.<region>-1.eventgrid.azure.net/api/events",
  "userAssignedIdentityClientId": null
}
```

For a user-assigned identity, replace `userAssignedIdentityClientId` with that identity's **client ID** after deployment. The role-assignment input remains the identity's **object/principal ID**.
