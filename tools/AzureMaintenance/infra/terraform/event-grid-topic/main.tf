locals {
  event_grid_data_sender_role_definition_id = "d5a91429-5739-47e2-a06b-3470a27159e7"
}

data "azurerm_subscription" "current" {}

resource "azurerm_eventgrid_topic" "this" {
  name                          = var.topic_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  input_schema                  = "EventGridSchema"
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = var.tags
}

resource "azurerm_role_assignment" "publisher" {
  count = var.publisher_principal_id == null ? 0 : 1

  scope              = azurerm_eventgrid_topic.this.id
  role_definition_id = "${data.azurerm_subscription.current.id}/providers/Microsoft.Authorization/roleDefinitions/${local.event_grid_data_sender_role_definition_id}"
  principal_id       = var.publisher_principal_id
  principal_type     = "ServicePrincipal"
}