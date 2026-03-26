param(
    [switch]$RunApp
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw "Python was not found in PATH. Install Python 3.10+ and try again."
}

$venvDir = Join-Path $scriptDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    & python -m venv $venvDir
}

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment creation failed."
}

Write-Host "Installing Python dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $scriptDir "requirements.txt")

$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract) {
    Write-Warning "Tesseract OCR was not found in PATH. OCR scanning will not work until it is installed."
    Write-Host "Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki"
} else {
    $tesseractVersion = (& tesseract --version | Select-Object -First 1)
    Write-Host "Found $tesseractVersion"
}

Write-Host "Setup complete."
Write-Host "To run the app manually:"
Write-Host "  .\.venv\Scripts\python.exe .\vendor_manager.py"

if ($RunApp) {
    & $venvPython (Join-Path $scriptDir "vendor_manager.py")
}
