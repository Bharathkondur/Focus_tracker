param(
    [string]$InstallDir = "$env:LOCALAPPDATA\MomentumCapture",
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceExe = Join-Path $sourceDir "MomentumCapture.exe"

if (-not (Test-Path $sourceExe)) {
    throw "MomentumCapture.exe was not found next to this installer script."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $InstallDir "MomentumCapture.exe") -Force

foreach ($asset in @("app_icon.ico", "Icon.png", "README.md", "RELEASE_READINESS.md")) {
    $path = Join-Path $sourceDir $asset
    if (Test-Path $path) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $InstallDir $asset) -Force
    }
}

$uninstallerSource = Join-Path $sourceDir "Uninstall_MomentumCapture.ps1"
if (Test-Path $uninstallerSource) {
    Copy-Item -LiteralPath $uninstallerSource -Destination (Join-Path $InstallDir "Uninstall_MomentumCapture.ps1") -Force
}

$shell = New-Object -ComObject WScript.Shell
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Momentum Capture.lnk"
$shortcut = $shell.CreateShortcut($startMenu)
$shortcut.TargetPath = Join-Path $InstallDir "MomentumCapture.exe"
$shortcut.WorkingDirectory = $InstallDir
$shortcut.IconLocation = Join-Path $InstallDir "app_icon.ico"
$shortcut.Description = "Momentum Capture"
$shortcut.Save()

if (-not $NoDesktopShortcut) {
    $desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Momentum Capture.lnk"
    $desktopShortcut = $shell.CreateShortcut($desktop)
    $desktopShortcut.TargetPath = Join-Path $InstallDir "MomentumCapture.exe"
    $desktopShortcut.WorkingDirectory = $InstallDir
    $desktopShortcut.IconLocation = Join-Path $InstallDir "app_icon.ico"
    $desktopShortcut.Description = "Momentum Capture"
    $desktopShortcut.Save()
}

@{
    installDir = $InstallDir
    installedAt = (Get-Date).ToString("s")
    version = "local"
} | ConvertTo-Json | Set-Content -Path (Join-Path $InstallDir "install.json") -Encoding UTF8

Write-Host "Momentum Capture installed to $InstallDir"
