#!/bin/bash
# ============================================================
# Run All Tests
# ============================================================

echo "Running backend tests..."
cd backend && pytest

echo "Running frontend tests..."
cd ../frontend && npm test

echo "All tests complete!"
