param(
    [string]$InstallDir = "$env:LOCALAPPDATA\MomentumCapture",
    [switch]$KeepData
)

$ErrorActionPreference = "Stop"

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Momentum Capture.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Momentum Capture.lnk"

Remove-Item -LiteralPath $startMenu -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktop -Force -ErrorAction SilentlyContinue

if (Test-Path $InstallDir) {
    if ($KeepData) {
        Get-ChildItem -LiteralPath $InstallDir -File |
            Where-Object { $_.Name -notin @("momentum.sqlite3", "momentum.sqlite3-shm", "momentum.sqlite3-wal") } |
            Remove-Item -Force
    } else {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }
}

Write-Host "Momentum Capture uninstalled."
