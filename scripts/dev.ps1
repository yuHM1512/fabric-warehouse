$ErrorActionPreference = "Stop"

if (!(Test-Path ".\\.venv\\Scripts\\python.exe")) {
  Write-Host "Missing venv. Create it first: python -m venv .venv" -ForegroundColor Yellow
  exit 1
}

$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m uvicorn fabric_warehouse.main:app --reload --host 0.0.0.0 --port 8014

# Reset WMS data for testing (purge/seed)
# Examples:
#   .\.venv\Scripts\python.exe -m fabric_warehouse.scripts.reset_wms_test_data --yes --ma-cay CAY001 CAY002 --recreate --nhu-cau NC-TEST --lot LOT-TEST
#   .\.venv\Scripts\python.exe -m fabric_warehouse.scripts.reset_wms_test_data --yes --all
