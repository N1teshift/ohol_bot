param(
    [string]$ConfigPath = "config\private_server.json"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$configFullPath = Join-Path $root $ConfigPath
$config = Get-Content $configFullPath -Raw | ConvertFrom-Json
$runtime = Join-Path $root $config.runtime_path
$serverExe = Join-Path $runtime "OneLifeServer.exe"

if (-not (Test-Path $serverExe)) {
    throw "Server binary not found. Run scripts\setup_private_server.ps1 first."
}

Push-Location $runtime
try {
    & $serverExe
}
finally {
    Pop-Location
}
