$ErrorActionPreference = "Stop"

Write-Host "Starting backend and frontend on Windows..."

$root = Resolve-Path "$PSScriptRoot\..\.."

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; .\venv\Scripts\Activate.ps1; python -m uvicorn api.main:app --reload --reload-dir api"

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"