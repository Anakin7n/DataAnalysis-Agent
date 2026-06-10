$env:PYTHONIOENCODING = "utf-8"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DataAnalysis-Agent" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] .env not found. Copy .env.example to .env and fill in API keys." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
    Write-Host "[OK] Using venv Python" -ForegroundColor Green
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Host "[ERROR] Python not found." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "[OK] Using system Python: $python" -ForegroundColor Green
}

Write-Host "[OK] Starting agent..." -ForegroundColor Green
Write-Host ""
& $python main.py

Write-Host ""
Write-Host "Agent stopped." -ForegroundColor Yellow
Read-Host "Press Enter to exit"
