param(
    [string]$SubscriptionId,
    [string]$OutputJson = (Join-Path $PSScriptRoot 'policiesreport.json'),
    [string]$OutputHtml = (Join-Path $PSScriptRoot 'policiesreport.html'),
    [switch]$NoHtml
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-AzureCli {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw 'Azure CLI (az) was not found. Run this script from Azure Cloud Shell or install Azure CLI first.'
    }
}

function Invoke-AzCliJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowEmpty
    )

    $rawOutput = & az @Arguments --output json 2>&1
    if ($LASTEXITCODE -ne 0) {
        $message = ($rawOutput | Out-String).Trim()
        throw "Azure CLI command failed: $message"
    }

    $jsonText = ($rawOutput | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        if ($AllowEmpty) { return $null }
        return @()
    }

    return $jsonText | ConvertFrom-Json
}

function Get-ScopeDetails {
    param([string]$ResourceId)

    if ([string]::IsNullOrWhiteSpace($ResourceId)) {
        return [pscustomobject]@{ Type = 'Unknown'; Value = $null; Raw = $null }
    }

    if ($ResourceId -match '/providers/') {
        return [pscustomobject]@{ Type = 'BuiltIn'; Value = 'Global'; Raw = $ResourceId }
    }

    $segments = $ResourceId.Trim('/').Split('/')
    $scopeType = 'Unknown'
    $scopeValue = $null

    for ($i = 0; $i -lt $segments.Length; $i++) {
        if ($segments[$i] -eq 'managementGroups' -and ($i + 1) -lt $segments.Length) {
            $scopeType = 'ManagementGroup'
            $scopeValue = $segments[$i + 1]
            break
        }

        if ($segments[$i] -eq 'subscriptions' -and ($i + 1) -lt $segments.Length) {
            $scopeType = 'Subscription'
            $scopeValue = $segments[$i + 1]
            break
        }

        if ($segments[$i] -eq 'resourceGroups' -and ($i + 1) -lt $segments.Length) {
            $scopeType = 'ResourceGroup'
            $scopeValue = $segments[$i + 1]
            break
        }
    }

    return [pscustomobject]@{ Type = $scopeType; Value = $scopeValue; Raw = $ResourceId }
}

function Resolve-DefinitionMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DefinitionId,
        [hashtable]$Cache,
        [string]$SubscriptionContext
    )

    if ($Cache.ContainsKey($DefinitionId)) {
        return $Cache[$DefinitionId]
    }

    $definitionType = if ($DefinitionId -match '/policySetDefinitions/') { 'Initiative' } else { 'Policy' }
    $segments = $DefinitionId.Trim('/').Split('/')
    $name = $segments[-1]

    $cliArgs = @()
    if ($definitionType -eq 'Initiative') {
        $cliArgs = @('policy', 'set-definition', 'show', '--name', $name)
    }
    else {
        $cliArgs = @('policy', 'definition', 'show', '--name', $name)
    }

    if ($SubscriptionContext) {
        $cliArgs += @('--subscription', $SubscriptionContext)
    }

    if ($DefinitionId -match '/managementGroups/') {
        $managementGroup = $segments[($segments.IndexOf('managementGroups') + 1)]
        if ($managementGroup) {
            $cliArgs += @('--management-group', $managementGroup)
        }
    }

    $response = $null
    try {
        $response = Invoke-AzCliJson -Arguments $cliArgs
    }
    catch {
        if ($definitionType -eq 'Initiative') {
            try {
                $response = @(Invoke-AzCliJson -Arguments @('policy', 'set-definition', 'list', '--subscription', $SubscriptionContext)) | Where-Object { $_.name -eq $name } | Select-Object -First 1
            }
            catch {
                $response = $null
            }
        }
    }

    if ($null -eq $response) {
        $displayName = $name
        $children = @()
    }
    else {
        $displayName = if ($response.PSObject.Properties.Name -contains 'displayName') { $response.displayName } else { $name }
        $children = @()

        if ($definitionType -eq 'Initiative' -and $null -ne $response.policyDefinitions) {
            foreach ($child in @($response.policyDefinitions)) {
                if ($null -eq $child.policyDefinitionId) { continue }

                $childMeta = Resolve-DefinitionMetadata -DefinitionId $child.policyDefinitionId -Cache $Cache -SubscriptionContext $SubscriptionContext
                $children += [pscustomobject]@{
                    Id = $child.policyDefinitionId
                    Name = $childMeta.Name
                    DisplayName = $childMeta.DisplayName
                    ReferenceId = $child.policyDefinitionReferenceId
                }
            }
        }
    }

    $meta = [pscustomobject]@{
        Id = $DefinitionId
        Name = $name
        DisplayName = $displayName
        Type = $definitionType
        CreationScope = (Get-ScopeDetails -ResourceId $DefinitionId)
        Children = $children
    }

    $Cache[$DefinitionId] = $meta
    return $meta
}

function ConvertTo-HtmlReport {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$ReportData
    )

    function Escape-Html {
        param([string]$Text)
        if ([string]::IsNullOrWhiteSpace($Text)) {
            return ''
        }

        return $Text.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;')
    }

    $items = @($ReportData.Items)
    $initiativeSections = New-Object System.Collections.Generic.List[string]
    $policySections = New-Object System.Collections.Generic.List[string]

    foreach ($item in $items | Where-Object { $_.Type -eq 'Initiative' } | Sort-Object DisplayName) {
        $scopeValues = New-Object System.Collections.Generic.List[string]
        foreach ($scope in @($item.AssignmentScopes)) {
            $scopeValues.Add($scope.Type + ':' + $scope.Value)
        }
        $scopes = @($scopeValues | Sort-Object -Unique)
        $policyList = New-Object System.Collections.Generic.List[string]

        foreach ($policy in @($item.Children)) {
            $policyList.Add('<li><strong>' + (Escape-Html $policy.DisplayName) + '</strong> - ' + (Escape-Html $policy.Id) + '</li>')
        }

        if ($policyList.Count -eq 0) {
            $policyList.Add('<li>No child policies were returned.</li>')
        }

        $assignmentList = New-Object System.Collections.Generic.List[string]
        foreach ($assignmentEntry in @($item.Assignments)) {
            $assignmentList.Add('<li>' + (Escape-Html $assignmentEntry.DefinitionName) + '</li>')
        }

        if ($assignmentList.Count -eq 0) {
            $assignmentList.Add('<li>No assignment details were returned.</li>')
        }

        $section = '<section class="card">' + [Environment]::NewLine +
            '<h3>' + (Escape-Html $item.DisplayName) + '</h3>' + [Environment]::NewLine +
            '<p><strong>Assignments:</strong> ' + $item.AssignmentCount + '</p>' + [Environment]::NewLine +
            '<p><strong>Creation scope:</strong> ' + (Escape-Html "$($item.CreationScope.Type):$($item.CreationScope.Value)") + '</p>' + [Environment]::NewLine +
            '<p><strong>Assignment scope(s):</strong> ' + (Escape-Html ($scopes -join ', ')) + '</p>' + [Environment]::NewLine +
            '<ul>' + ($assignmentList -join [Environment]::NewLine) + '</ul>' + [Environment]::NewLine +
            '<details>' + [Environment]::NewLine +
            '<summary>Policies included (' + $item.Children.Count + ')</summary>' + [Environment]::NewLine +
            '<ul>' + ($policyList -join [Environment]::NewLine) + '</ul>' + [Environment]::NewLine +
            '</details>' + [Environment]::NewLine +
            '</section>'

        $initiativeSections.Add($section)
    }

    foreach ($item in $items | Where-Object { $_.Type -eq 'Policy' } | Sort-Object DisplayName) {
        $scopeValues = New-Object System.Collections.Generic.List[string]
        foreach ($scope in @($item.AssignmentScopes)) {
            $scopeValues.Add($scope.Type + ':' + $scope.Value)
        }
        $scopes = @($scopeValues | Sort-Object -Unique)

        $assignmentList = New-Object System.Collections.Generic.List[string]
        foreach ($assignmentEntry in @($item.Assignments)) {
            $assignmentList.Add('<li>' + (Escape-Html $assignmentEntry.DefinitionName) + '</li>')
        }

        if ($assignmentList.Count -eq 0) {
            $assignmentList.Add('<li>No assignment details were returned.</li>')
        }

        $section = '<section class="card">' + [Environment]::NewLine +
            '<h3>' + (Escape-Html $item.DisplayName) + '</h3>' + [Environment]::NewLine +
            '<p><strong>Assignments:</strong> ' + $item.AssignmentCount + '</p>' + [Environment]::NewLine +
            '<p><strong>Creation scope:</strong> ' + (Escape-Html "$($item.CreationScope.Type):$($item.CreationScope.Value)") + '</p>' + [Environment]::NewLine +
            '<p><strong>Assignment scope(s):</strong> ' + (Escape-Html ($scopes -join ', ')) + '</p>' + [Environment]::NewLine +
            '<ul>' + ($assignmentList -join [Environment]::NewLine) + '</ul>' + [Environment]::NewLine +
            '</section>'

        $policySections.Add($section)
    }

    $html = @"
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Azure Policy Assignment Report</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 24px; background: #f5f7fb; color: #1f2937; }
    .container { max-width: 1400px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
    h1 { color: #0f6cbd; margin-top: 0; }
    .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin: 24px 0; }
    .summary .box { background: #f8fbff; border-left: 4px solid #0f6cbd; padding: 16px; border-radius: 8px; }
    .summary .box h2 { margin: 0 0 8px 0; font-size: 1.4rem; }
    .card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
    .card h3 { margin-top: 0; color: #0f6cbd; }
    ul { padding-left: 20px; }
    details { margin-top: 12px; }
    summary { cursor: pointer; font-weight: 600; color: #0f6cbd; }
    code { background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Azure Policy Assignment Report</h1>
    <p>Generated: $($ReportData.GeneratedAt)</p>
    <div class="summary">
      <div class="box"><h2>$($ReportData.TotalAssignments)</h2><p>Total assignments</p></div>
      <div class="box"><h2>$($ReportData.TotalInitiatives)</h2><p>Initiatives with assignments</p></div>
      <div class="box"><h2>$($ReportData.TotalPolicies)</h2><p>Policies with assignments</p></div>
      <div class="box"><h2>$($ReportData.SubscriptionId)</h2><p>Subscription</p></div>
    </div>
    <h2>Initiatives</h2>
    $($initiativeSections -join [Environment]::NewLine)
    <h2>Policies</h2>
    $($policySections -join [Environment]::NewLine)
  </div>
</body>
</html>
"@


    return $html
}

Assert-AzureCli

if ($SubscriptionId) {
    & az account set --subscription $SubscriptionId | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to set subscription to $SubscriptionId"
    }
}

$account = Invoke-AzCliJson -Arguments @('account', 'show')
$subscriptionId = if ($SubscriptionId) { $SubscriptionId } else { $account.id }

Write-Host "Collecting policy assignments for subscription $subscriptionId..." -ForegroundColor Cyan
$assignments = @(Invoke-AzCliJson -Arguments @('policy', 'assignment', 'list'))

if ($null -eq $assignments) {
    $assignments = @()
}

$definitionCache = @{}
$items = @{}

foreach ($assignment in $assignments) {
    $definitionId = $assignment.policyDefinitionId
    if ([string]::IsNullOrWhiteSpace($definitionId)) { continue }

    if (-not $items.ContainsKey($definitionId)) {
        $definitionMeta = Resolve-DefinitionMetadata -DefinitionId $definitionId -Cache $definitionCache -SubscriptionContext $subscriptionId
        $items[$definitionId] = [pscustomobject]@{
            Id = $definitionId
            Name = $definitionMeta.Name
            DisplayName = $definitionMeta.DisplayName
            Type = $definitionMeta.Type
            CreationScope = $definitionMeta.CreationScope
            AssignmentCount = 0
            AssignmentScopes = @()
            Assignments = @()
            Children = $definitionMeta.Children
        }
    }

    $item = $items[$definitionId]
    $item.AssignmentCount += 1
    $item.Assignments += [pscustomobject]@{
        AssignmentName = if ($assignment.name) { $assignment.name } else { $assignment.id }
        AssignmentId = if ($assignment.id) { $assignment.id } else { $null }
        DefinitionName = $item.DisplayName
        DefinitionId = $item.Id
    }

    $assignmentScope = Get-ScopeDetails -ResourceId $assignment.scope
    if ($assignmentScope.Type -ne 'Unknown' -and $assignmentScope.Value) {
        $item.AssignmentScopes += [pscustomobject]@{ Type = $assignmentScope.Type; Value = $assignmentScope.Value }
    }
}

$reportItems = @()
foreach ($item in $items.Values) {
    $uniqueScopes = @($item.AssignmentScopes | Sort-Object Type, Value -Unique)
    $reportItems += [pscustomobject]@{
        Id = $item.Id
        Name = $item.Name
        DisplayName = if ($item.DisplayName) { $item.DisplayName } else { $item.Name }
        Type = $item.Type
        CreationScope = $item.CreationScope
        AssignmentCount = $item.AssignmentCount
        AssignmentScopes = $uniqueScopes
        Assignments = @($item.Assignments)
        Children = $item.Children
    }
}

$sortedItems = @($reportItems | Sort-Object Type, DisplayName)
$report = [pscustomobject]@{
    GeneratedAt = (Get-Date).ToString('o')
    SubscriptionId = $subscriptionId
    TotalAssignments = $assignments.Count
    TotalInitiatives = @($sortedItems | Where-Object { $_.Type -eq 'Initiative' }).Count
    TotalPolicies = @($sortedItems | Where-Object { $_.Type -eq 'Policy' }).Count
    Items = $sortedItems
}

$report | ConvertTo-Json -Depth 10 | Set-Content -Path $OutputJson -Encoding UTF8
Write-Host "JSON report written to $OutputJson" -ForegroundColor Green

if (-not $NoHtml) {
    $html = ConvertTo-HtmlReport -ReportData $report
    Set-Content -Path $OutputHtml -Value $html -Encoding UTF8
    Write-Host "HTML report written to $OutputHtml" -ForegroundColor Green
}
