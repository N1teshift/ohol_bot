param(
    [Parameter(Mandatory = $true)]
    [string]$LogPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $LogPath)) {
    throw "Log file not found: $LogPath"
}

$lines = Get-Content $LogPath
$matches = $lines | Select-String -Pattern "New player (.+) connected as player ([0-9]+)"

$players = @{}
foreach ($match in $matches) {
    $account = $match.Matches[0].Groups[1].Value
    $playerId = $match.Matches[0].Groups[2].Value
    $players[$account] = $playerId
}

if ($players.Count -lt 2) {
    Write-Host "Only found $($players.Count) unique connected account(s)."
    $players.GetEnumerator() | ForEach-Object {
        Write-Host "$($_.Name) => player $($_.Value)"
    }
    exit 1
}

Write-Host "Found $($players.Count) unique connected accounts:"
$players.GetEnumerator() | Sort-Object Name | ForEach-Object {
    Write-Host "$($_.Name) => player $($_.Value)"
}
