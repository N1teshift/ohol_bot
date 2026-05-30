param(
    [string]$ConfigPath = "config\private_server.json",
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$configFullPath = Join-Path $root $ConfigPath
$config = Get-Content $configFullPath -Raw | ConvertFrom-Json

$source = $config.steam_install_path
$runtime = Join-Path $root $config.runtime_path

if (-not (Test-Path $source)) {
    throw "OHOL Steam install path not found: $source"
}

if ($Reset -and (Test-Path $runtime)) {
    Remove-Item $runtime -Recurse -Force
}

if (-not (Test-Path $runtime)) {
    New-Item -ItemType Directory -Path $runtime | Out-Null
    robocopy $source $runtime /MIR /XD "screenShots" "photoCache" "reverbCache" /XF "gameLog.txt" "yumlog.txt" "stdout.txt" "stderr.txt" | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
}

$serverSettingsPath = Join-Path $runtime "serverSettings"
$clientSettingsPath = Join-Path $runtime "settings"
New-Item -ItemType Directory -Force -Path $serverSettingsPath, $clientSettingsPath | Out-Null

$config.settings.PSObject.Properties | ForEach-Object {
    Set-Content -Path (Join-Path $serverSettingsPath $_.Name) -Value $_.Value -NoNewline
}

$config.client_settings.PSObject.Properties | ForEach-Object {
    Set-Content -Path (Join-Path $clientSettingsPath $_.Name) -Value $_.Value -NoNewline
}

Write-Host "Private server sandbox ready: $runtime"
Write-Host "Server: $($config.host):$($config.port)"
