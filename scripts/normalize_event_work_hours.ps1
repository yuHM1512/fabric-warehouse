param(
  [string]$FromDate,
  [string]$ToDate,
  [ValidateSet("fabric", "gon", "all")]
  [string]$Scope = "fabric",
  [switch]$Execute,
  [int]$SampleLimit = 50
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$python = ".\.venv\Scripts\python.exe"
if (!(Test-Path $python)) {
  Write-Host "Missing venv. Create it first: python -m venv .venv" -ForegroundColor Yellow
  exit 1
}

$env:PYTHONPATH = "src"
$argsList = @("-m", "fabric_warehouse.scripts.normalize_event_work_hours", "--scope", $Scope, "--sample-limit", "$SampleLimit")

if ($FromDate) {
  $argsList += @("--from-date", $FromDate)
}
if ($ToDate) {
  $argsList += @("--to-date", $ToDate)
}
if ($Execute) {
  $argsList += "--execute"
}

& $python $argsList
