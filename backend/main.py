"""
Backend Entry Point — delegates to app.main:app
Run with: uvicorn main:app --reload --port 8000
"""

from app.main import app  # noqa: F401
