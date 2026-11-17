#Requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter()]
    [string]$ConfigurationPath = "$env:ProgramData\AzureScheduledEvents\EventGridPublisher.json"
)

$ErrorActionPreference = 'Stop'

function Invoke-ImdsGet {
    param(
        [Parameter(Mandatory)]
        [string]$Uri,

        [Parameter()]
        [switch]$Raw
    )

    $request = [System.Net.HttpWebRequest]::Create($Uri)
    $request.Method = 'GET'
    $request.Headers.Add('Metadata', 'true')
    $request.Proxy = $null
    $request.Timeout = 5000
    $request.ReadWriteTimeout = 5000
    $response = $null
    $reader = $null

    try {
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        $content = $reader.ReadToEnd()

        if ($Raw) {
            return $content
        }

        return $content | ConvertFrom-Json
    }
    catch [System.Net.WebException] {
        $statusCode = $null
        $responseBody = ''

        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            $errorReader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            try {
                $responseBody = $errorReader.ReadToEnd()
            }
            finally {
                $errorReader.Dispose()
            }
        }

        throw "IMDS request failed with HTTP status '$statusCode': $responseBody If using the system-assigned identity, set userAssignedIdentityClientId to null. For a user-assigned identity, use its client ID, not its principal/object ID."
    }
    finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Dispose() }
    }
}

if (!(Test-Path -LiteralPath $ConfigurationPath -PathType Leaf)) {
    throw "Configuration file not found: $ConfigurationPath"
}

$configuration = Get-Content -LiteralPath $ConfigurationPath -Raw | ConvertFrom-Json
$topicEndpoint = [Uri]$configuration.topicEndpoint

if (!$topicEndpoint.IsAbsoluteUri -or $topicEndpoint.Scheme -ne 'https') {
    throw 'topicEndpoint must be an absolute HTTPS URI.'
}

if ($topicEndpoint.AbsolutePath.TrimEnd('/') -ne '/api/events' -or $topicEndpoint.Query) {
    throw 'topicEndpoint must end with /api/events and must not contain a query string.'
}

$resource = [Uri]::EscapeDataString('https://eventgrid.azure.net/')
$tokenUri = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=$resource"

if ($configuration.userAssignedIdentityClientId) {
    $clientId = [Uri]::EscapeDataString([string]$configuration.userAssignedIdentityClientId)
    $tokenUri += "&client_id=$clientId"
}

$tokenResponse = Invoke-ImdsGet -Uri $tokenUri
$publisherResourceId = (Invoke-ImdsGet -Uri 'http://169.254.169.254/metadata/instance/compute/resourceId?api-version=2021-02-01&format=text' -Raw).Trim()
$eventId = "synthetic-$([guid]::NewGuid())"

$event = @{
    id = $eventId
    subject = "$publisherResourceId/scheduledEvents/synthetic"
    eventType = 'AzureScheduledEvents.SyntheticTest'
    eventTime = (Get-Date).ToUniversalTime().ToString('o')
    data = @{
        publisherResourceId = $publisherResourceId
        synthetic = $true
        message = 'Synthetic Event Grid publisher test'
    }
    dataVersion = '1.0'
}

$body = '[' + ($event | ConvertTo-Json -Depth 10 -Compress) + ']'
$publishUri = "$($configuration.topicEndpoint)?api-version=2018-01-01"
$headers = @{ Authorization = "Bearer $($tokenResponse.access_token)" }

[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12

$response = Invoke-WebRequest `
    -UseBasicParsing `
    -Uri $publishUri `
    -Method POST `
    -Headers $headers `
    -ContentType 'application/json; charset=utf-8' `
    -Body $body `
    -TimeoutSec 10

[pscustomobject]@{
    EventId = $eventId
    EventType = $event.eventType
    TopicEndpoint = $configuration.topicEndpoint
    HttpStatusCode = [int]$response.StatusCode
    PublishedAtUtc = $event.eventTime
}