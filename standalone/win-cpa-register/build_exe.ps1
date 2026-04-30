$ErrorActionPreference = "Stop"

$ToolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ToolDir "..\..")
$VenvDir = Join-Path $ToolDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$DistDir = Join-Path $ToolDir "dist"
$BuildDir = Join-Path $ToolDir "build"
$SpecDir = Join-Path $ToolDir "spec"

if (-not (Test-Path $Python)) {
    if ($env:PYTHON) {
        & $env:PYTHON -m venv $VenvDir
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.13 -m venv $VenvDir
    } else {
        python -m venv $VenvDir
    }
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $ToolDir "requirements.txt")

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name cpa-register-win `
    --paths $RepoRoot `
    --collect-all curl_cffi `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $SpecDir `
    (Join-Path $ToolDir "win_cpa_register.py")

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name cpa-register-win-gui `
    --paths $RepoRoot `
    --collect-all curl_cffi `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $SpecDir `
    (Join-Path $ToolDir "win_cpa_register_gui.py")

$ConfigPath = Join-Path $DistDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item (Join-Path $ToolDir "config.example.json") $ConfigPath
}

Write-Host ""
Write-Host "Built: $(Join-Path $DistDir 'cpa-register-win.exe')"
Write-Host "Built: $(Join-Path $DistDir 'cpa-register-win-gui.exe')"
Write-Host "Config: $ConfigPath"
Write-Host "Run cpa-register-win-gui.exe for the interactive window."
