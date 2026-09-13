// Review-only example; creates an empty sandbox group and grants its identity
// read access to ONE existing Blob container. Does not deploy a firewall/APIM.
param location string = resourceGroup().location
param sandboxGroupName string
param storageAccountName string
param containerName string
resource group 'Microsoft.App/sandboxGroups@2026-02-01-preview' = {
  name: sandboxGroupName
  location: location
  identity: { type: 'SystemAssigned' }
}
resource account 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: account
  name: 'default'
}
resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: blobs
  name: containerName
}
var readerRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
resource readOnly 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, group.id, readerRole)
  scope: container
  properties: {
    principalId: group.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: readerRole
  }
}
output principalId string = group.identity.principalId
