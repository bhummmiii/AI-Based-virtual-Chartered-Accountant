# start-backend.ps1 — Start the CA Assistant backend server
# Run from the project root: .\start-backend.ps1

Write-Host "`n=== CA Assistant Backend ===" -ForegroundColor Cyan
Write-Host "Starting FastAPI on http://localhost:8000" -ForegroundColor Green
Write-Host "Swagger docs: http://localhost:8000/docs`n" -ForegroundColor Green

Set-Location "$PSScriptRoot\backend"

# Seed the database if it doesn't exist yet
if (-not (Test-Path "ca_assistant.db")) {
    Write-Host "First run — seeding database..." -ForegroundColor Yellow
    .\venv\Scripts\python.exe -m app.seed
    Write-Host ""
}

# Start the server
.\venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 8000
