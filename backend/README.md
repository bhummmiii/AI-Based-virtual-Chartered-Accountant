# ⚙️ Backend — AI-Based Chartered Accountant

## Overview

The backend API built with **FastAPI**, **SQLAlchemy**, **Alembic**, and **JWT authentication**. Provides RESTful APIs for all business modules including accounting, GST, tax, audit, and AI service orchestration.

## Directory Structure

```
backend/
├── app/
│   ├── api/
│   │   └── routers/           → API route handlers by module
│   │       ├── auth/          → Authentication & authorization
│   │       ├── clients/       → Client management
│   │       ├── accounting/    → Accounting operations
│   │       ├── gst/           → GST filing & tracking
│   │       ├── tax/           → Income tax management
│   │       ├── audit/         → Audit management
│   │       ├── reports/       → Report generation
│   │       ├── government/    → Government updates
│   │       ├── chatbot/       → AI chatbot endpoints
│   │       ├── ocr/           → OCR scanning endpoints
│   │       └── translation/   → Translation endpoints
│   ├── database/
│   │   ├── models/            → SQLAlchemy ORM models
│   │   ├── schemas/           → Pydantic request/response schemas
│   │   └── repositories/     → Data access layer (repository pattern)
│   ├── services/              → Business logic layer
│   ├── middleware/             → Custom middleware (CORS, logging, etc.)
│   ├── core/                  → Core utilities (config, events, exceptions)
│   ├── security/              → Authentication, authorization, JWT
│   ├── config/                → Application configuration
│   ├── scheduler/             → APScheduler background tasks
│   └── utils/                 → Utility functions
├── logs/                      → Application logs
├── tests/                     → Backend unit tests
├── main.py                    → FastAPI application entry point
├── requirements.txt           → Python dependencies
└── Dockerfile                 → Container configuration
```

## Getting Started

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Developer Guidelines

- Follow repository pattern for data access
- Keep business logic in services layer
- Use Pydantic schemas for all request/response validation
- Write unit tests for every endpoint
- Use dependency injection for database sessions
