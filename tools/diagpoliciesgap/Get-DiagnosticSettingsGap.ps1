# Get-DiagnosticSettingsGap.ps1
# Analyzes available diagnostic setting categories for resources and compares against policies

param(
    [switch]$RefreshCache,
    [string]$CacheFile = ".\DiagnosticSettingsCache.json"
)

#region Step 1: Get all unique resource types in the subscription
Write-Host "`n=== Step 1: Retrieving all resource types in your subscription ===" -ForegroundColor Cyan

$resources = Get-AzResource
$resourceTypes = $resources | Group-Object -Property ResourceType | Select-Object Name, Count | Sort-Object Count -Descending

Write-Host "`nFound $($resourceTypes.Count) unique resource types:" -ForegroundColor Green
$resourceTypes | Format-Table -AutoSize

#endregion

#region Step 2: Analyze all resource types that support diagnostic settings
Write-Host "`n=== Step 2: Analyzing all resource types for diagnostic settings support ===" -ForegroundColor Cyan

$resourceTypesWithDiagnostics = @()

# Check if cache exists and should be used
if (-not $RefreshCache -and (Test-Path $CacheFile)) {
    Write-Host "Loading cached diagnostic settings data from: $CacheFile" -ForegroundColor Yellow
    $cachedData = Get-Content $CacheFile | ConvertFrom-Json
    
    # Rebuild the objects with proper structure
    foreach ($cached in $cachedData) {
        # Find a current sample resource for this type (needed for matching with current subscription state)
        $sampleResource = $resources | Where-Object { $_.ResourceType -eq $cached.ResourceType } | Select-Object -First 1
        
        if ($sampleResource) {
            $resourceTypesWithDiagnostics += [PSCustomObject]@{
                ResourceType       = $cached.ResourceType
                ResourceCount      = ($resources | Where-Object { $_.ResourceType -eq $cached.ResourceType }).Count
                SampleResourceName = $sampleResource.Name
                SampleResourceId   = $sampleResource.ResourceId
                LogCategoryNames   = $cached.LogCategoryNames
                MetricCategoryNames = $cached.MetricCategoryNames
            }
            Write-Host "  [CACHED] $($cached.ResourceType) - $($cached.LogCategoryNames.Count) logs, $($cached.MetricCategoryNames.Count) metrics" -ForegroundColor Cyan
        }
    }
    
    Write-Host "`nLoaded $($resourceTypesWithDiagnostics.Count) resource types from cache." -ForegroundColor Cyan
    Write-Host "Use -RefreshCache to regenerate the cache." -ForegroundColor Gray
}
else {
    if ($RefreshCache) {
        Write-Host "Refreshing cache as requested..." -ForegroundColor Yellow
    }
    
    foreach ($resourceType in $resourceTypes) {
        # Get a sample resource of this type
        $sampleResource = $resources | Where-Object { $_.ResourceType -eq $resourceType.Name } | Select-Object -First 1
        
        if (-not $sampleResource) {
            continue
        }
        
        # Check if this resource type supports diagnostic settings
        try {
            $diagnosticCategories = Get-AzDiagnosticSettingCategory -ResourceId $sampleResource.ResourceId -ErrorAction Stop
            
            if ($diagnosticCategories -and $diagnosticCategories.Count -gt 0) {
                $logCategories = $diagnosticCategories | Where-Object { $_.CategoryType -eq "Logs" }
                $metricCategories = $diagnosticCategories | Where-Object { $_.CategoryType -eq "Metrics" }
                
                $resourceTypesWithDiagnostics += [PSCustomObject]@{
                    ResourceType        = $resourceType.Name
                    ResourceCount       = $resourceType.Count
                    SampleResourceName  = $sampleResource.Name
                    SampleResourceId    = $sampleResource.ResourceId
                    LogCategoryNames    = @($logCategories | Select-Object -ExpandProperty Name)
                    MetricCategoryNames = @($metricCategories | Select-Object -ExpandProperty Name)
                }
                
                Write-Host "  [OK] $($resourceType.Name) - $($logCategories.Count) logs, $($metricCategories.Count) metrics" -ForegroundColor Green
            }
        }
        catch {
            Write-Host "  [--] $($resourceType.Name) - No diagnostic settings support" -ForegroundColor DarkGray
        }
    }
    
    # Save to cache
    Write-Host "`nSaving diagnostic settings data to cache: $CacheFile" -ForegroundColor Yellow
    $cacheData = $resourceTypesWithDiagnostics | Select-Object ResourceType, LogCategoryNames, MetricCategoryNames
    $cacheData | ConvertTo-Json -Depth 10 | Out-File $CacheFile -Encoding UTF8
    
    Write-Host "`nFound $($resourceTypesWithDiagnostics.Count) resource types with diagnostic settings support." -ForegroundColor Cyan
}

#endregion

#region Step 3: Get diagnostic setting categories for each resource type
Write-Host "`n=== Step 3: Diagnostic setting categories by resource type ===" -ForegroundColor Cyan

foreach ($rt in $resourceTypesWithDiagnostics) {
    Write-Host "`n$($rt.ResourceType)" -ForegroundColor Yellow
    Write-Host "  Sample: $($rt.SampleResourceName)" -ForegroundColor Gray
    
    if ($rt.LogCategoryNames -and $rt.LogCategoryNames.Count -gt 0) {
        Write-Host "  Log Categories:" -ForegroundColor White
        $rt.LogCategoryNames | ForEach-Object { Write-Host "    - $_" -ForegroundColor Gray }
    }
    
    if ($rt.MetricCategoryNames -and $rt.MetricCategoryNames.Count -gt 0) {
        Write-Host "  Metric Categories:" -ForegroundColor White
        $rt.MetricCategoryNames | ForEach-Object { Write-Host "    - $_" -ForegroundColor Gray }
    }
}

#endregion

# #region Step 4: Get current diagnostic settings for all resources
# Write-Host "`n=== Step 4: Current diagnostic settings on resources ===" -ForegroundColor Cyan

# $allResourceSettings = @()

# foreach ($rt in $resourceTypesWithDiagnostics) {
#     try {
#         $currentSettings = Get-AzDiagnosticSetting -ResourceId $rt.SampleResourceId -ErrorAction Stop
        
#         $enabledLogs = @()
#         $enabledMetrics = @()
        
#         if ($currentSettings) {
#             foreach ($setting in $currentSettings) {
#                 $enabledLogs += ($setting.Log | Where-Object { $_.Enabled } | Select-Object -ExpandProperty Category)
#                 $enabledMetrics += ($setting.Metric | Where-Object { $_.Enabled } | Select-Object -ExpandProperty Category)
#             }
#         }
        
#         $rt | Add-Member -NotePropertyName "CurrentSettings" -NotePropertyValue $currentSettings -Force
#         $rt | Add-Member -NotePropertyName "EnabledLogCategories" -NotePropertyValue ($enabledLogs | Select-Object -Unique) -Force
#         $rt | Add-Member -NotePropertyName "EnabledMetricCategories" -NotePropertyValue ($enabledMetrics | Select-Object -Unique) -Force
        
#         $settingsCount = if ($currentSettings) { $currentSettings.Count } else { 0 }
#         Write-Host "  $($rt.ResourceType): $settingsCount diagnostic setting(s) configured" -ForegroundColor $(if ($settingsCount -gt 0) { "Green" } else { "Yellow" })
#     }
#     catch {
#         $rt | Add-Member -NotePropertyName "CurrentSettings" -NotePropertyValue $null -Force
#         $rt | Add-Member -NotePropertyName "EnabledLogCategories" -NotePropertyValue @() -Force
#         $rt | Add-Member -NotePropertyName "EnabledMetricCategories" -NotePropertyValue @() -Force
#         Write-Host "  $($rt.ResourceType): No diagnostic settings configured" -ForegroundColor Yellow
#     }
# }

# #endregion

#region Step 5: Get policies related to diagnostic settings
Write-Host "`n=== Step 5: Analyzing policies for diagnostic settings ===" -ForegroundColor Cyan

# Get all policy assignments
$policyAssignments = Get-AzPolicyAssignment

# Filter for diagnostic-related policies
$diagnosticPolicies = @()

foreach ($assignment in $policyAssignments) {
    try {
        $definitionId = $assignment.PolicyDefinitionId
        $definition = $null
        $policyRules = @()
        
        # Check if this is a policy set (initiative) or single policy
        if ($definitionId -match "policySetDefinitions") {
            # It's a policy set - get individual policies within it
            $policySet = Get-AzPolicySetDefinition -Id $definitionId -ErrorAction Stop
            
            if ($policySet -and $policySet.PolicyDefinition) {
                foreach ($policyRef in $policySet.PolicyDefinition) {
                    $innerDef = Get-AzPolicyDefinition -Id $policyRef.policyDefinitionId -ErrorAction SilentlyContinue
                    if ($innerDef -and $innerDef.PolicyRule) {
                        $policyRuleJson = $innerDef.PolicyRule | ConvertTo-Json -Depth 20
                        
                        # Check if this inner policy is related to diagnostic settings
                        if ($policyRuleJson -match "diagnosticSettings|DiagnosticSettings|Microsoft.Insights/diagnosticSettings") {
                            $diagnosticPolicies += [PSCustomObject]@{
                                AssignmentName        = $assignment.Name
                                DisplayName           = $assignment.DisplayName
                                DefinitionId          = $policyRef.policyDefinitionId
                                DefinitionName        = $innerDef.Name
                                DefinitionDisplayName = $innerDef.DisplayName
                                Effect                = $innerDef.Parameter.effect.DefaultValue
                                Description           = $innerDef.Description
                                PolicyRule            = $policyRuleJson
                                PolicyRuleObject      = $innerDef.PolicyRule
                                IsFromPolicySet       = $true
                                PolicySetName         = $policySet.DisplayName
                            }
                        }
                    }
                }
            }
        }
        else {
            # It's a single policy definition
            $definition = Get-AzPolicyDefinition -Id $definitionId -ErrorAction Stop
            
            if ($definition -and $definition.PolicyRule) {
                $policyRule = $definition.PolicyRule | ConvertTo-Json -Depth 20
                
                # Check if policy is related to diagnostic settings
                if ($policyRule -match "diagnosticSettings|DiagnosticSettings|Microsoft.Insights/diagnosticSettings") {
                    $diagnosticPolicies += [PSCustomObject]@{
                        AssignmentName        = $assignment.Name
                        DisplayName           = $assignment.DisplayName
                        DefinitionId          = $assignment.PolicyDefinitionId
                        DefinitionName        = $definition.Name
                        DefinitionDisplayName = $definition.DisplayName
                        Effect                = $definition.Parameter.effect.DefaultValue
                        Description           = $definition.Description
                        PolicyRule            = $policyRule
                        PolicyRuleObject      = $definition.PolicyRule
                        IsFromPolicySet       = $false
                        PolicySetName         = $null
                    }
                }
            }
        }
    }
    catch {
        # Skip errors
        Write-Host "  Skipping assignment: $($assignment.Name) - $($_.Exception.Message)" -ForegroundColor DarkGray
        continue
    }
}

if ($diagnosticPolicies.Count -gt 0) {
    Write-Host "`nFound $($diagnosticPolicies.Count) diagnostic-related policies:" -ForegroundColor Green
    
    foreach ($policy in $diagnosticPolicies) {
        Write-Host "`n  Policy: $($policy.DisplayName ?? $policy.AssignmentName)" -ForegroundColor Yellow
        if ($policy.IsFromPolicySet) {
            Write-Host "    From Policy Set: $($policy.PolicySetName)" -ForegroundColor Cyan
        }
        Write-Host "    Definition: $($policy.DefinitionDisplayName ?? $policy.DefinitionName)" -ForegroundColor Gray
        Write-Host "    Effect: $($policy.Effect)" -ForegroundColor Gray
        
        # Try to extract which categories are configured in the policy
        if ($policy.PolicyRule -match '"category":\s*"([^"]+)"') {
            Write-Host "    Categories mentioned in policy:" -ForegroundColor White
            $catMatches = [regex]::Matches($policy.PolicyRule, '"category":\s*"([^"]+)"')
            $catMatches | ForEach-Object { Write-Host "      - $($_.Groups[1].Value)" -ForegroundColor Gray }
        }
    }
}
else {
    Write-Host "`nNo diagnostic-related policies found in assignments." -ForegroundColor Yellow
    Write-Host "`nSkipping policy gap analysis - no policies to compare against." -ForegroundColor Yellow
    Write-Host "`n=== Analysis Complete ===" -ForegroundColor Cyan
    exit
}

#endregion

#region Step 6: Policy Gap Analysis - Find categories missing from policies
Write-Host "`n=== Step 6: Policy Gap Analysis ===" -ForegroundColor Cyan

# Extract categories and resource types from each policy
$policyCategories = @()

foreach ($policy in $diagnosticPolicies) {
    $policyJson = $policy.PolicyRule
    $policyRuleObj = $policy.PolicyRuleObject
    
    $policyResourceType = "Unknown"
    
    # Use the stored PolicyRuleObject to find the resource type
    if ($policyRuleObj -and $policyRuleObj.if) {
        $ifCondition = $policyRuleObj.if
        
        # Handle allOf conditions (array of conditions)
        if ($ifCondition.allOf) {
            foreach ($condition in $ifCondition.allOf) {
                if ($condition.field -eq "type" -and $condition.equals) {
                    $policyResourceType = $condition.equals.ToLower()
                    break
                }
            }
        }
        # Handle direct field condition
        elseif ($ifCondition.field -eq "type" -and $ifCondition.equals) {
            $policyResourceType = $ifCondition.equals.ToLower()
        }
    }
    
    # Extract all category references from the policy
    $categoryMatches = [regex]::Matches($policyJson, '"category":\s*"([^"]+)"')
    $categories = $categoryMatches | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
    
    # Extract categories from categoryGroup if present
    $categoryGroupMatches = [regex]::Matches($policyJson, '"categoryGroup":\s*"([^"]+)"')
    $categoryGroups = $categoryGroupMatches | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
    
    $policyCategories += [PSCustomObject]@{
        PolicyName        = $policy.DisplayName ?? $policy.AssignmentName
        DefinitionName    = $policy.DefinitionDisplayName ?? $policy.DefinitionName
        ResourceType      = $policyResourceType
        LogCategories     = $categories
        CategoryGroups    = $categoryGroups
        IsFromPolicySet   = $policy.IsFromPolicySet
        PolicySetName     = $policy.PolicySetName
    }
}

Write-Host "`nPolicy category configuration:" -ForegroundColor Green
foreach ($pc in $policyCategories) {
    Write-Host "`n  Policy: $($pc.PolicyName)" -ForegroundColor Yellow
    Write-Host "    Resource Type: $($pc.ResourceType)" -ForegroundColor Gray
    if ($pc.LogCategories.Count -gt 0) {
        Write-Host "    Categories: $($pc.LogCategories -join ', ')" -ForegroundColor Gray
    }
    if ($pc.CategoryGroups.Count -gt 0) {
        Write-Host "    Category Groups: $($pc.CategoryGroups -join ', ')" -ForegroundColor Cyan
    }
}

# Compare policy categories against available categories for each resource type
Write-Host "`n--- Policy vs Available Categories Gap ---" -ForegroundColor Cyan

# Debug: Show all policy resource types for comparison
Write-Host "`nDEBUG - Policy Resource Types extracted:" -ForegroundColor Magenta
foreach ($pc in $policyCategories) {
    Write-Host "  '$($pc.ResourceType)' -> $($pc.PolicyName)" -ForegroundColor Magenta
}

$policyGapResults = @()

foreach ($rt in $resourceTypesWithDiagnostics) {
    # Get available categories for this resource type
    $availableLogCategories = $rt.LogCategoryNames ?? @()
    
    # Debug: Show what we're trying to match
    Write-Host "`nDEBUG - Trying to match resource: '$($rt.ResourceType)'" -ForegroundColor Magenta
    
    # Find policies that target this resource type (case-insensitive comparison)
    $matchingPolicies = $policyCategories | Where-Object { 
        $rtLower = $rt.ResourceType.ToLower()
        $policyTypeLower = $_.ResourceType.ToLower()
        $match = $rtLower -eq $policyTypeLower
        if ($match) {
            Write-Host "  DEBUG - MATCH FOUND: '$rtLower' with policy type: '$policyTypeLower'" -ForegroundColor Green
        }
        $match
    }
    
    Write-Host "  DEBUG - Matching policies count: $($matchingPolicies.Count)" -ForegroundColor Magenta
    
    if ($matchingPolicies.Count -gt 0) {
        # Process each matching policy independently
        $policyIndex = 0
        foreach ($mp in $matchingPolicies) {
            $policyIndex++
            
            # Check if policy uses categoryGroup (like "allLogs") which covers all categories
            $usesAllLogs = $mp.CategoryGroups -contains "allLogs" -or $mp.CategoryGroups -contains "AllLogs"
            $usesAudit = $mp.CategoryGroups -contains "audit" -or $mp.CategoryGroups -contains "Audit"
            
            # Show resource type header only for first policy, then indent subsequent ones
            if ($policyIndex -eq 1) {
                Write-Host "`n$($rt.ResourceType)" -ForegroundColor Yellow
            }
            
            Write-Host "`n  [$policyIndex/$($matchingPolicies.Count)] Policy: $($mp.PolicyName)" -ForegroundColor Cyan
            Write-Host "      Definition: $($mp.DefinitionName)" -ForegroundColor Gray
            
            if ($usesAllLogs) {
                Write-Host "      Category Groups: allLogs" -ForegroundColor Cyan
                Write-Host "      Status: Uses 'allLogs' category group - All categories covered" -ForegroundColor Green
                
                $policyGapResults += [PSCustomObject]@{
                    ResourceType        = $rt.ResourceType
                    PolicyName          = $mp.PolicyName
                    DefinitionName      = $mp.DefinitionName
                    AvailableCategories = $availableLogCategories
                    PolicyCategories    = @("allLogs")
                    CategoryGroups      = $mp.CategoryGroups
                    MissingCategories   = @()
                    UsesAllLogs         = $true
                    HasGap              = $false
                }
            }
            elseif ($usesAudit) {
                # "audit" category group - only covers audit-related categories, not all
                Write-Host "      Category Groups: $($mp.CategoryGroups -join ', ')" -ForegroundColor Cyan
                Write-Host "      Status: Uses 'audit' category group - Only audit categories covered" -ForegroundColor Yellow
                Write-Host "      Available Categories: $($availableLogCategories.Count) ($($availableLogCategories -join ', '))" -ForegroundColor Gray
                Write-Host "      Note: 'audit' group may not cover all available categories" -ForegroundColor Yellow
                
                $policyGapResults += [PSCustomObject]@{
                    ResourceType        = $rt.ResourceType
                    PolicyName          = $mp.PolicyName
                    DefinitionName      = $mp.DefinitionName
                    AvailableCategories = $availableLogCategories
                    PolicyCategories    = @()
                    CategoryGroups      = $mp.CategoryGroups
                    MissingCategories   = @()  # Can't determine without knowing which categories are in audit group
                    UsesAllLogs         = $false
                    UsesAuditGroup      = $true
                    HasGap              = $false  # Considered compliant if using audit group
                }
            }
            else {
                # Find categories in available but not in policy
                $policyCats = $mp.LogCategories ?? @()
                $missingFromPolicy = $availableLogCategories | Where-Object { $_ -notin $policyCats }
                
                $hasGap = $missingFromPolicy.Count -gt 0
                
                Write-Host "      Available Categories: $($availableLogCategories.Count)" -ForegroundColor Gray
                Write-Host "      Policy Categories: $($policyCats.Count)" -ForegroundColor Gray
                
                if ($mp.CategoryGroups.Count -gt 0) {
                    Write-Host "      Category Groups: $($mp.CategoryGroups -join ', ')" -ForegroundColor Cyan
                }
                
                if ($policyCats.Count -gt 0) {
                    Write-Host "      Specific Categories: $($policyCats -join ', ')" -ForegroundColor Gray
                }
                
                if ($hasGap) {
                    Write-Host "      MISSING from Policy: $($missingFromPolicy -join ', ')" -ForegroundColor Red
                }
                else {
                    Write-Host "      Status: All available categories are covered by policy" -ForegroundColor Green
                }
                
                $policyGapResults += [PSCustomObject]@{
                    ResourceType        = $rt.ResourceType
                    PolicyName          = $mp.PolicyName
                    DefinitionName      = $mp.DefinitionName
                    AvailableCategories = $availableLogCategories
                    PolicyCategories    = $policyCats
                    CategoryGroups      = $mp.CategoryGroups
                    MissingCategories   = $missingFromPolicy
                    UsesAllLogs         = $false
                    HasGap              = $hasGap
                }
            }
        }
    }
    else {
        Write-Host "`n$($rt.ResourceType)" -ForegroundColor Yellow
        Write-Host "  NO POLICY FOUND for this resource type" -ForegroundColor Red
        Write-Host "  Available Categories: $($availableLogCategories -join ', ')" -ForegroundColor Gray
        
        $policyGapResults += [PSCustomObject]@{
            ResourceType        = $rt.ResourceType
            PolicyName          = $null
            AvailableCategories = $availableLogCategories
            PolicyCategories    = @()
            MissingCategories   = $availableLogCategories
            UsesAllLogs         = $false
            HasGap              = $true
        }
    }
}

# Summary
$policiesWithGaps = $policyGapResults | Where-Object { $_.HasGap }
$resourcesWithoutPolicy = $policyGapResults | Where-Object { $null -eq $_.PolicyName }

Write-Host "`n--- Summary ---" -ForegroundColor Cyan
Write-Host "Total resource types with diagnostic support: $($resourceTypesWithDiagnostics.Count)" -ForegroundColor White
Write-Host "Resource types without matching policy: $($resourcesWithoutPolicy.Count)" -ForegroundColor $(if ($resourcesWithoutPolicy.Count -gt 0) { "Red" } else { "Green" })
Write-Host "Policies with missing categories: $($policiesWithGaps.Count)" -ForegroundColor $(if ($policiesWithGaps.Count -gt 0) { "Red" } else { "Green" })

#endregion

#region Step 7: Export results
Write-Host "`n=== Step 7: Export Results ===" -ForegroundColor Cyan

$exportPath = ".\DiagnosticSettingsPolicyGapAnalysis_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"

$results = [PSCustomObject]@{
    AnalysisDate                    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    TotalResourceTypes              = $resourceTypes.Count
    ResourceTypesWithDiagnostics    = $resourceTypesWithDiagnostics.Count
    ResourceTypesWithoutPolicy      = $resourcesWithoutPolicy.Count
    PoliciesWithMissingCategories   = ($policiesWithGaps | Where-Object { $null -ne $_.PolicyName }).Count
    DiagnosticPolicies              = $diagnosticPolicies | Select-Object AssignmentName, DisplayName, DefinitionDisplayName, Effect
    PolicyGapAnalysis               = $policyGapResults | ForEach-Object {
        [PSCustomObject]@{
            ResourceType        = $_.ResourceType
            PolicyName          = $_.PolicyName
            DefinitionName      = $_.DefinitionName
            AvailableCategories = $_.AvailableCategories
            PolicyCategories    = $_.PolicyCategories
            MissingCategories   = $_.MissingCategories
            UsesAllLogs         = $_.UsesAllLogs
            HasGap              = $_.HasGap
        }
    }
}

$results | ConvertTo-Json -Depth 10 | Out-File -FilePath $exportPath -Encoding UTF8

Write-Host "`nResults exported to: $exportPath" -ForegroundColor Green

Write-Host "`n=== Analysis Complete ===" -ForegroundColor Cyan
