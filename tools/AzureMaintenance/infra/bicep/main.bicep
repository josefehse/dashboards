targetScope = 'resourceGroup'

@description('Name of the Azure Monitor data collection rule.')
param dataCollectionRuleName string

@description('Azure region for the data collection rule. This must match the Log Analytics workspace region.')
param location string

@description('Resource ID of the existing Log Analytics workspace that receives the events.')
@minLength(1)
param logAnalyticsWorkspaceResourceId string

@description('Optional tags to apply to the data collection rule.')
param tags object = {}

var streamName = 'Microsoft-Event'
var destinationName = 'logAnalytics'
var dataSourceName = 'azureScheduledEvents'
var xPathQuery = 'Application!*[System[Provider[@Name=\'AzureScheduledEvents\'] and (EventID=0 or EventID=1234)]]'

resource dataCollectionRule 'Microsoft.Insights/dataCollectionRules@2024-03-11' = {
  name: dataCollectionRuleName
  location: location
  kind: 'Windows'
  tags: tags
  properties: {
    dataSources: {
      windowsEventLogs: [
        {
          name: dataSourceName
          streams: [
            streamName
          ]
          xPathQueries: [
            xPathQuery
          ]
        }
      ]
    }
    destinations: {
      logAnalytics: [
        {
          name: destinationName
          workspaceResourceId: logAnalyticsWorkspaceResourceId
        }
      ]
    }
    dataFlows: [
      {
        streams: [
          streamName
        ]
        destinations: [
          destinationName
        ]
      }
    ]
  }
}

output dataCollectionRuleId string = dataCollectionRule.id
output dataCollectionRuleName string = dataCollectionRule.name
output dataCollectionRuleImmutableId string? = dataCollectionRule.properties.?immutableId
