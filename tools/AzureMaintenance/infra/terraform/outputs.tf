output "data_collection_rule_id" {
  description = "Resource ID of the data collection rule."
  value       = azurerm_monitor_data_collection_rule.this.id
}

output "data_collection_rule_name" {
  description = "Name of the data collection rule."
  value       = azurerm_monitor_data_collection_rule.this.name
}

output "data_collection_rule_immutable_id" {
  description = "Immutable ID used by Azure Monitor Agent for the data collection rule."
  value       = azurerm_monitor_data_collection_rule.this.immutable_id
}