@{
    # Script module file associated with this manifest
    RootModule        = 'AUM-Helpers.psm1'

    # Version number of this module
    ModuleVersion     = '1.0.0'

    # ID used to uniquely identify this module
    GUID              = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

    # Author of this module
    Author            = 'AUM Maintenance Team'

    # Description of the functionality provided by this module
    Description       = 'Shared helper functions for Azure Update Manager (AUM) maintenance event handling in Azure Functions.'

    # Minimum version of the PowerShell engine required by this module
    PowerShellVersion = '7.0'

    # Functions to export from this module
    FunctionsToExport = @(
        'Get-ManagedIdentityToken'
        'Invoke-AzureRestApi'
        'ConvertFrom-VMResourceId'
        'Get-SubscriptionIdFromResourceId'
        'Get-MaintenanceConfigurationId'
        'Get-VMResourceIdsFromEvent'
        'Get-VMsFromMaintenanceConfiguration'
        'Get-MaintenanceEventVMs'
        'Get-VMPowerState'
        'Get-VMDetails'
        'Start-VMAsync'
        'Stop-VMAsync'
    )

    # Cmdlets to export from this module
    CmdletsToExport   = @()

    # Variables to export from this module
    VariablesToExport = @()

    # Aliases to export from this module
    AliasesToExport   = @()

    # Private data to pass to the module
    PrivateData       = @{
        PSData = @{
            Tags       = @('Azure', 'AUM', 'Maintenance', 'VirtualMachines')
            ProjectUri = ''
        }
    }
}
