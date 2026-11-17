variable "data_collection_rule_name" {
  type        = string
  description = "Name of the Azure Monitor data collection rule."
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group where the data collection rule will be created."
}

variable "location" {
  type        = string
  description = "Azure region for the data collection rule. This must match the Log Analytics workspace region."
}

variable "log_analytics_workspace_resource_id" {
  type        = string
  description = "Resource ID of the existing Log Analytics workspace that receives the events."

  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.OperationalInsights/workspaces/[^/]+$", var.log_analytics_workspace_resource_id))
    error_message = "log_analytics_workspace_resource_id must be a full Microsoft.OperationalInsights/workspaces resource ID."
  }
}

variable "tags" {
  type        = map(string)
  description = "Optional tags to apply to the data collection rule."
  default     = {}
}