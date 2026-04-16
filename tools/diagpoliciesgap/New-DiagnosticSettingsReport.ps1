# New-DiagnosticSettingsReport.ps1
# Generates an HTML report from the diagnostic settings gap analysis JSON

param(
    [string]$JsonFile,
    [string]$OutputFile
)

# If no JSON file specified, find the most recent one
if (-not $JsonFile) {
    $jsonFiles = Get-ChildItem -Path ".\DiagnosticSettingsPolicyGapAnalysis_*.json" | Sort-Object LastWriteTime -Descending
    if ($jsonFiles.Count -eq 0) {
        Write-Host "No analysis JSON files found. Please run Get-DiagnosticSettingsGap.ps1 first." -ForegroundColor Red
        exit 1
    }
    $JsonFile = $jsonFiles[0].FullName
    Write-Host "Using most recent analysis: $($jsonFiles[0].Name)" -ForegroundColor Cyan
}

# If no output file specified, generate one based on the JSON filename
if (-not $OutputFile) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($JsonFile)
    $OutputFile = ".\$baseName.html"
}

# Load the JSON data
Write-Host "Loading analysis data from: $JsonFile" -ForegroundColor Cyan
$data = Get-Content $JsonFile | ConvertFrom-Json

# Categorize the results
$resourcesWithGaps = @()
$compliantResources = @()
$resourcesWithoutPolicy = @()

foreach ($item in $data.PolicyGapAnalysis) {
    if ($null -eq $item.PolicyName) {
        $resourcesWithoutPolicy += $item
    }
    elseif ($item.HasGap) {
        $resourcesWithGaps += $item
    }
    else {
        $compliantResources += $item
    }
}

Write-Host "Generating HTML report..." -ForegroundColor Cyan
Write-Host "  Resources with gaps: $($resourcesWithGaps.Count)" -ForegroundColor Yellow
Write-Host "  Compliant resources: $($compliantResources.Count)" -ForegroundColor Green
Write-Host "  Resources without policy: $($resourcesWithoutPolicy.Count)" -ForegroundColor Red

# Generate HTML
$html = @"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diagnostic Settings Policy Gap Analysis Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #0078d4;
            border-bottom: 3px solid #0078d4;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        
        .metadata {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 30px;
            border-left: 4px solid #0078d4;
        }
        
        .metadata p {
            margin: 5px 0;
        }
        
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .summary-card {
            padding: 20px;
            border-radius: 5px;
            color: white;
            text-align: center;
        }
        
        .summary-card.danger {
            background-color: #d13438;
        }
        
        .summary-card.warning {
            background-color: #ff8c00;
        }
        
        .summary-card.success {
            background-color: #107c10;
        }
        
        .summary-card.info {
            background-color: #0078d4;
        }
        
        .summary-card h3 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .summary-card p {
            font-size: 1.1em;
        }
        
        .section {
            margin-bottom: 40px;
        }
        
        .section-header {
            background-color: #0078d4;
            color: white;
            padding: 15px;
            border-radius: 5px 5px 0 0;
            font-size: 1.3em;
            font-weight: bold;
        }
        
        .section-header.danger {
            background-color: #d13438;
        }
        
        .section-header.warning {
            background-color: #ff8c00;
        }
        
        .section-header.success {
            background-color: #107c10;
        }
        
        .section-content {
            border: 1px solid #dee2e6;
            border-top: none;
            border-radius: 0 0 5px 5px;
        }
        
        .resource-item {
            padding: 20px;
            border-bottom: 1px solid #dee2e6;
        }
        
        .resource-item:last-child {
            border-bottom: none;
        }
        
        .resource-item:hover {
            background-color: #f8f9fa;
        }
        
        .resource-type {
            font-size: 1.2em;
            font-weight: bold;
            color: #0078d4;
            margin-bottom: 10px;
        }
        
        .policy-info {
            background-color: #e7f3ff;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            border-left: 4px solid #0078d4;
        }
        
        .policy-name {
            font-weight: bold;
            color: #333;
        }
        
        .definition-name {
            font-size: 0.9em;
            color: #666;
            margin-left: 20px;
        }
        
        .categories {
            margin-top: 10px;
        }
        
        .category-label {
            font-weight: bold;
            margin-top: 10px;
            margin-bottom: 5px;
            color: #555;
        }
        
        .category-list {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-top: 5px;
        }
        
        .category-badge {
            padding: 5px 10px;
            border-radius: 3px;
            font-size: 0.85em;
            display: inline-block;
        }
        
        .category-badge.available {
            background-color: #e0e0e0;
            color: #333;
        }
        
        .category-badge.policy {
            background-color: #107c10;
            color: white;
        }
        
        .category-badge.missing {
            background-color: #d13438;
            color: white;
            font-weight: bold;
        }
        
        .category-badge.all-logs {
            background-color: #0078d4;
            color: white;
            font-weight: bold;
        }
        
        .no-items {
            padding: 20px;
            text-align: center;
            color: #666;
            font-style: italic;
        }
        
        .collapsible {
            cursor: pointer;
            user-select: none;
        }
        
        .collapsible:after {
            content: ' ▼';
            font-size: 0.8em;
        }
        
        .collapsible.collapsed:after {
            content: ' ▶';
        }
        
        .collapsible-content {
            max-height: none;
            overflow: visible;
            transition: max-height 0.3s ease-out;
        }
        
        .collapsible-content.collapsed {
            max-height: 0;
            overflow: hidden;
        }
        
        @media print {
            body {
                background-color: white;
            }
            
            .container {
                box-shadow: none;
            }
            
            .collapsible-content {
                max-height: none !important;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Diagnostic Settings Policy Gap Analysis Report</h1>
        
        <div class="metadata">
            <p><strong>Analysis Date:</strong> $($data.AnalysisDate)</p>
            <p><strong>Total Resource Types:</strong> $($data.TotalResourceTypes)</p>
            <p><strong>Resource Types with Diagnostic Support:</strong> $($data.ResourceTypesWithDiagnostics)</p>
        </div>
        
        <div class="summary">
            <div class="summary-card danger">
                <h3>$($resourcesWithoutPolicy.Count)</h3>
                <p>Resources Without Policy</p>
            </div>
            <div class="summary-card warning">
                <h3>$($resourcesWithGaps.Count)</h3>
                <p>Policies with Gaps</p>
            </div>
            <div class="summary-card success">
                <h3>$($compliantResources.Count)</h3>
                <p>Compliant Policies</p>
            </div>
            <div class="summary-card info">
                <h3>$($data.DiagnosticPolicies.Count)</h3>
                <p>Total Diagnostic Policies</p>
            </div>
        </div>
"@

# Section 1: Resources without any policy (highest priority)
$html += @"
        <div class="section">
            <div class="section-header danger collapsible" onclick="toggleSection('no-policy')">
                🚨 Resources Without Policy ($($resourcesWithoutPolicy.Count))
            </div>
            <div id="no-policy" class="section-content collapsible-content">
"@

if ($resourcesWithoutPolicy.Count -eq 0) {
    $html += @"
                <div class="no-items">No resources without policy coverage. Excellent!</div>
"@
}
else {
    foreach ($item in ($resourcesWithoutPolicy | Sort-Object ResourceType)) {
        $availableCount = ($item.AvailableCategories | Measure-Object).Count
        
        $html += @"
                <div class="resource-item">
                    <div class="resource-type">$($item.ResourceType)</div>
                    <p style="color: #d13438; font-weight: bold;">⚠️ No policy assigned for this resource type</p>
"@
        
        if ($availableCount -gt 0) {
            $html += @"
                    <div class="categories">
                        <div class="category-label">Available Log Categories ($availableCount):</div>
                        <div class="category-list">
"@
            foreach ($cat in $item.AvailableCategories) {
                $html += @"
                            <span class="category-badge available">$cat</span>
"@
            }
            $html += @"
                        </div>
                    </div>
"@
        }
        
        $html += @"
                </div>
"@
    }
}

$html += @"
            </div>
        </div>
"@

# Section 2: Policies with gaps (medium priority)
$html += @"
        <div class="section">
            <div class="section-header warning collapsible" onclick="toggleSection('with-gaps')">
                ⚠️ Policies with Missing Categories ($($resourcesWithGaps.Count))
            </div>
            <div id="with-gaps" class="section-content collapsible-content">
"@

if ($resourcesWithGaps.Count -eq 0) {
    $html += @"
                <div class="no-items">No policies with missing categories. Great!</div>
"@
}
else {
    foreach ($item in ($resourcesWithGaps | Sort-Object ResourceType, PolicyName)) {
        $missingCount = ($item.MissingCategories | Measure-Object).Count
        $policyCount = ($item.PolicyCategories | Measure-Object).Count
        $availableCount = ($item.AvailableCategories | Measure-Object).Count
        
        $html += @"
                <div class="resource-item">
                    <div class="resource-type">$($item.ResourceType)</div>
                    <div class="policy-info">
                        <div class="policy-name">Policy: $($item.PolicyName)</div>
"@
        
        if ($item.DefinitionName) {
            $html += @"
                        <div class="definition-name">Definition: $($item.DefinitionName)</div>
"@
        }
        
        $html += @"
                    </div>
                    <p style="color: #ff8c00; font-weight: bold;">⚠️ $missingCount categor$(if ($missingCount -ne 1) { "ies are" } else { "y is" }) missing from this policy</p>
                    
                    <div class="categories">
                        <div class="category-label">Missing Categories ($missingCount):</div>
                        <div class="category-list">
"@
        
        foreach ($cat in $item.MissingCategories) {
            $html += @"
                            <span class="category-badge missing">$cat</span>
"@
        }
        
        $html += @"
                        </div>
                    </div>
"@
        
        if ($policyCount -gt 0) {
            $html += @"
                    <div class="categories">
                        <div class="category-label">Currently Covered by Policy ($policyCount):</div>
                        <div class="category-list">
"@
            foreach ($cat in $item.PolicyCategories) {
                $html += @"
                            <span class="category-badge policy">$cat</span>
"@
            }
            $html += @"
                        </div>
                    </div>
"@
        }
        
        $html += @"
                </div>
"@
    }
}

$html += @"
            </div>
        </div>
"@

# Section 3: Compliant policies (lowest priority, collapsed by default)
$html += @"
        <div class="section">
            <div class="section-header success collapsible collapsed" onclick="toggleSection('compliant')">
                ✅ Compliant Policies ($($compliantResources.Count))
            </div>
            <div id="compliant" class="section-content collapsible-content collapsed">
"@

if ($compliantResources.Count -eq 0) {
    $html += @"
                <div class="no-items">No compliant policies found.</div>
"@
}
else {
    foreach ($item in ($compliantResources | Sort-Object ResourceType, PolicyName)) {
        $availableCount = ($item.AvailableCategories | Measure-Object).Count
        
        $html += @"
                <div class="resource-item">
                    <div class="resource-type">$($item.ResourceType)</div>
                    <div class="policy-info">
                        <div class="policy-name">Policy: $($item.PolicyName)</div>
"@
        
        if ($item.DefinitionName) {
            $html += @"
                        <div class="definition-name">Definition: $($item.DefinitionName)</div>
"@
        }
        
        $html += @"
                    </div>
"@
        
        if ($item.UsesAllLogs) {
            $html += @"
                    <p style="color: #107c10; font-weight: bold;">✅ Uses 'allLogs' category group - All $availableCount categories covered</p>
                    <div class="categories">
                        <div class="category-list">
                            <span class="category-badge all-logs">allLogs</span>
                        </div>
                    </div>
"@
        }
        else {
            $policyCount = ($item.PolicyCategories | Measure-Object).Count
            $html += @"
                    <p style="color: #107c10; font-weight: bold;">✅ All available categories are covered by this policy</p>
                    <div class="categories">
                        <div class="category-label">Covered Categories ($policyCount):</div>
                        <div class="category-list">
"@
            foreach ($cat in $item.PolicyCategories) {
                $html += @"
                            <span class="category-badge policy">$cat</span>
"@
            }
            $html += @"
                        </div>
                    </div>
"@
        }
        
        $html += @"
                </div>
"@
    }
}

$html += @"
            </div>
        </div>
        
        <script>
            function toggleSection(sectionId) {
                var content = document.getElementById(sectionId);
                var header = content.previousElementSibling;
                
                if (content.classList.contains('collapsed')) {
                    content.classList.remove('collapsed');
                    header.classList.remove('collapsed');
                } else {
                    content.classList.add('collapsed');
                    header.classList.add('collapsed');
                }
            }
        </script>
    </div>
</body>
</html>
"@

# Write the HTML file
$html | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "`nHTML report generated: $OutputFile" -ForegroundColor Green
Write-Host "Open in browser to view the report." -ForegroundColor Cyan

# Optionally open in default browser
$openBrowser = Read-Host "`nOpen report in browser? (Y/N)"
if ($openBrowser -eq 'Y' -or $openBrowser -eq 'y') {
    Start-Process $OutputFile
}
