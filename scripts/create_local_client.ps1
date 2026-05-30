param(
    [string]$ClientId = "bot_001",
    [string]$ConfigPath = "config\local_clients.json",
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$configFullPath = Join-Path $root $ConfigPath
$config = Get-Content $configFullPath -Raw | ConvertFrom-Json
$client = $config.clients | Where-Object { $_.id -eq $ClientId } | Select-Object -First 1

if ($null -eq $client) {
    throw "Unknown local client id: $ClientId"
}

$source = Join-Path $root $config.source_client
$clientsRoot = Join-Path $root $config.clients_root
$target = Join-Path $clientsRoot $client.folder

if (-not (Test-Path (Join-Path $source "OneLife.exe"))) {
    throw "Source client sandbox not found. Run scripts\setup_private_server.ps1 first."
}

if ($Reset -and (Test-Path $target)) {
    Remove-Item $target -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $clientsRoot | Out-Null

if (-not (Test-Path $target)) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    robocopy $source $target /MIR /XD "screenShots" "photoCache" "reverbCache" /XF "gameLog.txt" "yumlog.txt" "stdout.txt" "stderr.txt" | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
}

$settingsPath = Join-Path $target "settings"
New-Item -ItemType Directory -Force -Path $settingsPath | Out-Null

Set-Content -Path (Join-Path $settingsPath "email.ini") -Value $client.email -NoNewline
Set-Content -Path (Join-Path $settingsPath "accountKey.ini") -Value $client.account_key -NoNewline
if ($client.PSObject.Properties.Name -contains "server_password") {
    Set-Content -Path (Join-Path $settingsPath "serverPassword.ini") -Value $client.server_password -NoNewline
}
Set-Content -Path (Join-Path $settingsPath "useCustomServer.ini") -Value "1" -NoNewline
Set-Content -Path (Join-Path $settingsPath "customServerAddress.ini") -Value $client.host -NoNewline
Set-Content -Path (Join-Path $settingsPath "customServerPort.ini") -Value ([string]$client.port) -NoNewline
Set-Content -Path (Join-Path $settingsPath "vogModeOn.ini") -Value "1" -NoNewline

Write-Host "Local client ready: $target"
Write-Host "Credentials: $($client.email) / $($client.account_key)"
