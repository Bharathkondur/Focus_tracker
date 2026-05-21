param(
    [string]$Version = (Get-Date -Format "yyyy.MM.dd-HHmm"),
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

python -m unittest discover -s tests -v
python -m compileall momentum tests

if (-not $SkipBuild) {
    python -m pip install --user --upgrade -r "$repoRoot\requirements.txt"
    python -m pip install --user --upgrade pyinstaller
    $iconArgs = @()
    if (Test-Path "$repoRoot\app_icon.ico") {
        $iconArgs = @("--icon=$repoRoot\app_icon.ico")
    }
    python -m PyInstaller `
        --onefile `
        --windowed `
        --name MomentumCapture `
        @iconArgs `
        --collect-all tokenizers `
        --distpath "$repoRoot\dist" `
        --workpath "$repoRoot\build" `
        --specpath "$repoRoot" `
        "$repoRoot\momentum_capture.py"

    if (-not (Test-Path "$repoRoot\dist\MomentumCapture.exe")) {
        throw "PyInstaller did not produce dist\MomentumCapture.exe"
    }
    Copy-Item -LiteralPath "$repoRoot\dist\MomentumCapture.exe" -Destination "$repoRoot\MomentumCapture.exe" -Force
    Remove-Item -LiteralPath "$repoRoot\dist" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "$repoRoot\build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "$repoRoot\MomentumCapture.spec" -Force -ErrorAction SilentlyContinue
}

$exe = Join-Path $repoRoot "MomentumCapture.exe"
if (-not (Test-Path $exe)) {
    throw "MomentumCapture.exe not found. Run Build_Capture_Exe.bat first or omit -SkipBuild."
}

$releaseRoot = Join-Path $repoRoot "release"
$stage = Join-Path $releaseRoot "MomentumCapture-$Version"
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Copy-Item -LiteralPath $exe -Destination (Join-Path $stage "MomentumCapture.exe") -Force
foreach ($asset in @("app_icon.ico", "Icon.png", "README.md", "AI_ARCHITECTURE.md", "RELEASE_READINESS.md")) {
    if (Test-Path $asset) {
        Copy-Item -LiteralPath $asset -Destination (Join-Path $stage $asset) -Force
    }
}

Copy-Item -LiteralPath (Join-Path $repoRoot "installer\Install_MomentumCapture.ps1") -Destination $stage -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "installer\Uninstall_MomentumCapture.ps1") -Destination $stage -Force

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stage "MomentumCapture.exe")
"MomentumCapture.exe  $($hash.Hash)" | Set-Content -Path (Join-Path $stage "SHA256SUMS.txt") -Encoding ASCII

$zip = Join-Path $releaseRoot "MomentumCapture-$Version.zip"
if (Test-Path $zip) {
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip

Write-Host "Release package created:"
Write-Host "  $zip"
Write-Host "Install with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\Install_MomentumCapture.ps1"
