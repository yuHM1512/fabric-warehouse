$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (!(Test-Path ".\\.venv\\Scripts\\python.exe")) {
  Write-Host "Missing venv. Create it first: python -m venv .venv" -ForegroundColor Yellow
  exit 1
}

$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m fabric_warehouse.scripts.reset_wms_test_data @args

