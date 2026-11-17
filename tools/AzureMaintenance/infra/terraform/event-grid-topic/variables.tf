variable "topic_name" {
  type        = string
  description = "Name of the Event Grid custom topic. The name must be unique within the Azure region."

  validation {
    condition     = can(regex("^[A-Za-z0-9-]{3,50}$", var.topic_name))
    error_message = "topic_name must contain 3 to 50 alphanumeric or hyphen characters."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group where the Event Grid custom topic will be created."
}

variable "location" {
  type        = string
  description = "Azure region where the Event Grid custom topic will be created."
}

variable "publisher_principal_id" {
  type        = string
  description = "Optional object/principal ID of a managed identity that will publish events."
  default     = null
  nullable    = true

  validation {
    condition     = var.publisher_principal_id == null || can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$", var.publisher_principal_id))
    error_message = "publisher_principal_id must be null or a managed identity object/principal GUID."
  }
}

variable "tags" {
  type        = map(string)
  description = "Optional tags to apply to the Event Grid custom topic."
  default     = {}
}