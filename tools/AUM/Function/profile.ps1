# Azure Functions profile.ps1
#
# This profile.ps1 will get executed every "cold start" of your Function App.
# "cold start" occurs when:
#
# * A Function App starts up for the very first time
# * A Function App starts up after being de-allocated due to inactivity
#
# You can define helper functions, run commands, or specify environment variables
# NOTE: any variables defined that are not environment variables will get reset after the first execution

# NOTE: This Function App uses REST APIs with Managed Identity tokens directly,
# so Az PowerShell modules are NOT required. This avoids module loading overhead
# on Flex Consumption plans.

# Load shared AUM helper module
$modulePath = Join-Path $PSScriptRoot "Modules" "AUM-Helpers" "AUM-Helpers.psd1"
if (Test-Path $modulePath) {
    Import-Module $modulePath -Force
    Write-Host "Loaded AUM-Helpers module from: $modulePath"
} else {
    Write-Warning "AUM-Helpers module not found at: $modulePath"
}

# You can also define functions or aliases that can be referenced in any of your PowerShell functions.
