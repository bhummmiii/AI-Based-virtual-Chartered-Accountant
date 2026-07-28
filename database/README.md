# 🗄️ Database — AI-Based Chartered Accountant

## Overview

PostgreSQL database configuration including schemas, migrations (Alembic), seed data, backup scripts, and Entity-Relationship Diagrams.

## Directory Structure

```
database/
├── schema/        → SQL schema definitions
├── migrations/    → Alembic migration files
├── seed/          → Initial seed data
├── backup/        → Database backup files (gitignored)
├── scripts/       → Database utility scripts
└── ERD/           → Entity-Relationship Diagrams
```

## Setup

```bash
# Initialize Alembic (already configured)
cd backend
alembic init alembic

# Create a migration
alembic revision --autogenerate -m "Initial migration"

# Run migrations
alembic upgrade head

# Seed database
python -m scripts.seed
```

## Tables Overview

| Table           | Description                    |
|-----------------|--------------------------------|
| users           | User accounts & authentication |
| clients         | Client company profiles        |
| accounting      | Journal entries & ledger       |
| gst_returns     | GST filing records             |
| tax_records     | Income tax computations        |
| audit_reports   | Audit findings & reports       |
| documents       | Uploaded document metadata     |
| chat_history    | AI chatbot conversation logs   |
| gov_updates     | Scraped government updates     |
