param(
    [string]$ClientId = "bot_001",
    [string]$ConfigPath = "config\local_clients.json"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$configFullPath = Join-Path $root $ConfigPath
$config = Get-Content $configFullPath -Raw | ConvertFrom-Json
$client = $config.clients | Where-Object { $_.id -eq $ClientId } | Select-Object -First 1

if ($null -eq $client) {
    throw "Unknown local client id: $ClientId"
}

$clientPath = Join-Path (Join-Path $root $config.clients_root) $client.folder
$exePath = Join-Path $clientPath $client.executable

if (-not (Test-Path $exePath)) {
    throw "Local client binary not found. Run scripts\create_local_client.ps1 -ClientId $ClientId first."
}

Start-Process $exePath -WorkingDirectory $clientPath
Write-Host "Launched local client $ClientId from $clientPath"
