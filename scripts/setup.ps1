# ============================================================
# Project Setup Script (Windows)
# ============================================================
# Usage: .\scripts\setup.ps1

Write-Host "Setting up AI-Based Chartered Accountant..."

# Backend setup
Set-Location backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Frontend setup
Set-Location ..\frontend
npm install

Write-Host "Setup complete!"
