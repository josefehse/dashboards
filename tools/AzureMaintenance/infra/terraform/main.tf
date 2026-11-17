locals {
  stream_name      = "Microsoft-Event"
  destination_name = "logAnalytics"
  data_source_name = "azureScheduledEvents"
  x_path_query     = "Application!*[System[Provider[@Name='AzureScheduledEvents'] and (EventID=0 or EventID=1234)]]"
}

resource "azurerm_monitor_data_collection_rule" "this" {
  name                = var.data_collection_rule_name
  resource_group_name = var.resource_group_name
  location            = var.location
  kind                = "Windows"
  tags                = var.tags

  destinations {
    log_analytics {
      name                  = local.destination_name
      workspace_resource_id = var.log_analytics_workspace_resource_id
    }
  }

  data_flow {
    streams      = [local.stream_name]
    destinations = [local.destination_name]
  }

  data_sources {
    windows_event_log {
      name           = local.data_source_name
      streams        = [local.stream_name]
      x_path_queries = [local.x_path_query]
    }
  }
}