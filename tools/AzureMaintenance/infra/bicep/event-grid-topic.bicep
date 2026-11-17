targetScope = 'resourceGroup'

@description('Name of the Event Grid custom topic. The name must be unique within the Azure region.')
@minLength(3)
@maxLength(50)
param topicName string

@description('Azure region where the Event Grid custom topic will be created.')
param location string = resourceGroup().location

@description('Optional object/principal ID of a managed identity that will publish events. Leave empty to omit the role assignment.')
param publisherPrincipalId string = ''

@description('Optional tags to apply to the Event Grid custom topic.')
param tags object = {}

var eventGridDataSenderRoleDefinitionId = 'd5a91429-5739-47e2-a06b-3470a27159e7'

resource topic 'Microsoft.EventGrid/topics@2025-02-15' = {
  name: topicName
  location: location
  tags: tags
  properties: {
    inputSchema: 'EventGridSchema'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource publisherRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(publisherPrincipalId)) {
  name: guid(topic.id, eventGridDataSenderRoleDefinitionId, publisherPrincipalId)
  scope: topic
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      eventGridDataSenderRoleDefinitionId
    )
    principalId: publisherPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output topicId string = topic.id
output topicName string = topic.name
output topicEndpoint string = topic.properties.endpoint
output publisherConfiguration object = {
  topicEndpoint: topic.properties.endpoint
  userAssignedIdentityClientId: null
}
