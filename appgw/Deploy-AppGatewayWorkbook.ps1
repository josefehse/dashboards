param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$Location,
    
    [Parameter(Mandatory=$false)]
    [string]$WorkbookName = "Application Gateway Configuration Dashboard"
)

# Read the workbook JSON
$workbookContent = Get-Content -Path ".\application-gateway-workbook.json" -Raw

# Create the workbook resource
$workbookId = (New-Guid).ToString()
$workbookResourceName = "appgw-config-workbook-$workbookId"

$workbookProperties = @{
    displayName = $WorkbookName
    serializedData = $workbookContent
    category = "workbook"
    sourceId = "azure monitor"
    version = "1.0"
}

# Deploy using Azure CLI or REST API
az resource create `
    --resource-group $ResourceGroupName `
    --resource-type "Microsoft.Insights/workbooks" `
    --name $workbookResourceName `
    --location $Location `
    --properties (@{
        displayName = $WorkbookName
        serializedData = $workbookContent
        category = "Azure Monitor"
        sourceId = "Azure Monitor"
    } | ConvertTo-Json -Depth 100)

Write-Host "Workbook deployed successfully!" -ForegroundColor Green
Write-Host "You can find it in Azure Portal > Monitor > Workbooks > $WorkbookName" -ForegroundColor Cyan
