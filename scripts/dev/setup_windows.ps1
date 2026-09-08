$ErrorActionPreference = "Stop"

Write-Host "Setting up F1 Race Winner Predictor project on Windows..."

# get project root
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

Write-Host "`n[1/4] Creating Python virtual environment..."

if (!(Test-Path ".\venv")) {
    python -m venv venv
} else {
    Write-Host "venv already exists, skipping creation."
}

Write-Host "`n[2/4] Activating virtual environment..."
& .\venv\Scripts\Activate.ps1

Write-Host "`n[3/4] Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "`n[4/4] Installing frontend dependencies..."
Set-Location "$root\frontend"
npm install

Write-Host "`nSetup complete."
Write-Host ""
Write-Host "Backend:"
Write-Host "python -m uvicorn api.main:app --reload --reload-dir api"
Write-Host ""
Write-Host "Frontend:"
Write-Host "cd frontend && npm run dev"