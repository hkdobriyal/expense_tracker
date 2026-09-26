# Starts the API, the background worker and the Vite dev server in three windows.
# Usage (from the repository root):  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
# Optional: -DataDir C:\path\to\throwaway  to run against a separate database.
param([string]$DataDir = "")

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  Write-Host "Creating Python virtual environment…"
  python -m venv (Join-Path $backend ".venv")
  & $python -m pip install -r (Join-Path $backend "requirements.txt")
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
  Push-Location $frontend; npm install; Pop-Location
}

$envPrefix = if ($DataDir) { "`$env:DATA_DIR='$DataDir'; " } else { "" }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "${envPrefix}Set-Location '$backend'; & '$python' -m uvicorn app.main:app --reload --port 8000"
Start-Sleep -Seconds 3   # let the API run migrations first
Start-Process powershell -ArgumentList "-NoExit", "-Command", "${envPrefix}Set-Location '$backend'; & '$python' -m app.worker"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev"
Write-Host "API http://localhost:8000/api/docs · App http://localhost:5173"
