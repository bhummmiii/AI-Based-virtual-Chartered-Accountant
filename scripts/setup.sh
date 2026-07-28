#!/bin/bash
# ============================================================
# Project Setup Script
# ============================================================
# Usage: ./scripts/setup.sh

echo "Setting up AI-Based Chartered Accountant..."

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install

echo "Setup complete!"
