$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "Removing macOS metadata and caches..."

Get-ChildItem -Recurse -Force -Filter "._*" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Force -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path ".\frontend\.next") {
    Remove-Item -Recurse -Force .\frontend\.next
}

Write-Host "Cleanup complete."