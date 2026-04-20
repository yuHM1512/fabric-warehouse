$ErrorActionPreference = "Stop"

if (!(Test-Path ".\\.venv\\Scripts\\python.exe")) {
  Write-Host "Missing venv. Create it first: python -m venv .venv" -ForegroundColor Yellow
  exit 1
}

$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m alembic @Args

