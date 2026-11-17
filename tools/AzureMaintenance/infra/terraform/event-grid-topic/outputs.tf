output "topic_id" {
  description = "Resource ID of the Event Grid custom topic."
  value       = azurerm_eventgrid_topic.this.id
}

output "topic_name" {
  description = "Name of the Event Grid custom topic."
  value       = azurerm_eventgrid_topic.this.name
}

output "topic_endpoint" {
  description = "HTTPS publishing endpoint for the Event Grid custom topic."
  value       = azurerm_eventgrid_topic.this.endpoint
}

output "publisher_configuration" {
  description = "Configuration object accepted by SchServiceEventGrid.ps1 when using system-assigned identity."
  value = {
    topicEndpoint                = azurerm_eventgrid_topic.this.endpoint
    userAssignedIdentityClientId = null
  }
}