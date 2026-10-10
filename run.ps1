# ==============================================================================
# BULK CERTIFICATE GENERATION PLATFORM - RUNNER SCRIPT (POWERSHELL)
# ==============================================================================

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " STARTING BULK CERTIFICATE GENERATION PLATFORM" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[!] Virtual environment not found at $VenvPython" -ForegroundColor Yellow
    Write-Host "[*] Creating virtual environment and installing dependencies..." -ForegroundColor Yellow
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

Write-Host "[+] Using Python: $VenvPython" -ForegroundColor Green
Write-Host "[+] Project Root: $ProjectRoot" -ForegroundColor Green
Write-Host ""
Write-Host ">> Server listening at: http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host ">> Swagger Docs at:     http://127.0.0.1:8000/docs" -ForegroundColor Yellow
Write-Host ">> Press Ctrl+C in this terminal to stop the server" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

& $VenvPython -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
