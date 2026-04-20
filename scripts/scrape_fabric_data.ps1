$ErrorActionPreference = "Stop"

if (!(Test-Path ".\\.venv\\Scripts\\python.exe")) {
  Write-Host "Missing venv. Create it first: python -m venv .venv" -ForegroundColor Yellow
  exit 1
}

if ([string]::IsNullOrWhiteSpace($env:HACHIBA_COOKIE)) {
  Write-Host "Missing env var HACHIBA_COOKIE (Cookie header). Example:" -ForegroundColor Yellow
  Write-Host "  `$env:HACHIBA_COOKIE = 'csrftoken=...; sessionid=...'" -ForegroundColor Yellow
  exit 1
}

$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m fabric_warehouse.scripts.scrape_fabric_data --cookie $env:HACHIBA_COOKIE @Args

