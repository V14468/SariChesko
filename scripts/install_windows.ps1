# SariChesko Windows Setup Script
# Creates a virtual environment and installs dependencies to run from source.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "Setting up SariChesko in $ProjectRoot..." -ForegroundColor Cyan

# 1. Create virtual environment if it does not exist
$VenvDir = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment at $VenvDir..." -ForegroundColor Yellow
    python -m venv $VenvDir
} else {
    Write-Host "Virtual environment already exists at $VenvDir." -ForegroundColor Green
}

# 2. Activate virtual environment
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & $ActivateScript
} else {
    Write-Error "Activation script not found: $ActivateScript"
    exit 1
}

# 3. Upgrade pip and install requirements
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
python -m pip install -e $ProjectRoot

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host " Setup complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "To run SariChesko, run:" -ForegroundColor Cyan
Write-Host "  python -m sarichesko.app"
Write-Host "  or: sarichesko"
Write-Host ""
