# 🏛️ FinLedger AI — Virtual Chartered Accountant Platform

> **An enterprise-grade, statutory double-entry accounting, intelligent document ingestion (OCR), and Indian GST compliance platform built for Chartered Accountants, tax practitioners, and Indian enterprises.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg?style=flat&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=flat&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6.0+-646CFF.svg?style=flat&logo=vite&logoColor=white)](https://vitejs.dev/)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-3.4+-06B6D4.svg?style=flat&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Pytest-167%2F167%20Passed-brightgreen.svg?style=flat&logo=pytest&logoColor=white)](backend/tests/)

---

## 📌 Executive Summary

**FinLedger AI** is an intelligent FinTech system designed to automate the entire lifecycle of financial accounting and statutory GST compliance under the **Central Goods and Services Tax (CGST) Act, 2017** and Indian double-entry bookkeeping standards.

The platform bridges raw physical/digital documents (tax invoices, credit/debit notes, e-invoices, e-way bills, and challans) directly to an immutable **Double-Entry General Ledger**, and derives statutory **GST Returns (GSTR-1, GSTR-2B, GSTR-3B)** exclusively from posted ledger entries — guaranteeing mathematical equilibrium, single-source-of-truth integrity, and complete auditability.

---

## 🏗️ End-to-End System Architecture & Data Flow

```mermaid
graph TD
    A[Document Upload / Scan<br/>PDF, PNG, JPG, WebP] -->|300 DPI Preprocessing & OpenCV| B[Layered OCR Engine<br/>Native PDF + Tesseract Multi-PSM]
    B -->|Structured Field Extraction| C[UploadedDocument Repository<br/>Client Scoped, Metadata Stored]
    C -->|Statutory Validation Gate| D{Pre-Posting Validation}
    D -->|Error: Mismatch, Duplicate, Client Mismatch| E[Status: needs_review<br/>Flagged Discrepancy]
    D -->|Non-Invoice: EWB, Challan, HSN| F[Isolated Source Document<br/>Stored, Zero Voucher Impact]
    D -->|Valid Invoice / Note| G[Accounting Draft Service<br/>Templates T1 - T6]
    G -->|Debits-First Ordering & Split Tax Accounts| H[Journal Entry Engine<br/>General Ledger Posting]
    H -->|Strict Reference Link| I[Posted Vouchers<br/>Immutable GL Entries]
    I -->|Single Source of Truth: Read Ledger Only| J[GST Reconciliation Service]
    J -->|B2B, B2C Large > 1L, B2C Small, CDNR| K[GSTR-1 Table Outward]
    J -->|Inward Vouchers T2, T5, T6 Only| L[Purchase Register / GSTR-2B ITC]
    J -->|Sec 49 Utilization: IGST -> CGST -> SGST| M[GSTR-3B Cash & Set-Off]
    M -->|Auto-Populated & Period Locked| N[Statutory Return Filing Modal & UI]
```

---

## 🛠️ Technology Stack & Languages

### 1. Backend Core & APIs
- **Language**: **Python 3.11+**
- **Web Framework**: **FastAPI** (asynchronous API endpoints, dependency injection, OpenAPI/Swagger docs at `/docs`)
- **ORM & Database Layer**: **SQLAlchemy 2.0** (declarative mapping, strict typed sessions, connection pooling)
- **Database Migrations**: **Alembic**
- **Databases**:
  - **PostgreSQL 16** (`ca_assistant_db` via `psycopg3` driver) for development and production workloads.
  - **SQLite** (`sqlite:///:memory:`) for high-speed, isolated unit and regression test suites.
- **Data Validation & Settings**: **Pydantic v2** & `pydantic-settings`
- **Security & Auth**: **JWT (JSON Web Tokens)** via `python-jose`, password hashing via `passlib[bcrypt]`

### 2. Document Processing & AI Pipeline
- **Computer Vision & Image Preprocessing**: **OpenCV (`cv2`)**, **NumPy**, **Pillow (PIL)** (grayscale conversion, adaptive Otsu thresholding, noise reduction, 300 DPI rasterization via `pdf2image`)
- **PDF Extraction**: **PyPDF2** for native text/metadata extraction
- **OCR Engine**: **Tesseract OCR (v5.x)** with multi-Page Segmentation Modes (PSM 3, PSM 4, PSM 6) for robust printed and tabular handwriting extraction
- **Generative AI & LLM Advisory**: **Google Gemini API** (`gemini-flash-lite-latest`) for regulatory advisory and conversational CA assistance

### 3. Frontend Application
- **Language**: **TypeScript 5.x** & **JavaScript (ESNext)**
- **UI Framework**: **React 18**
- **Bundler & Dev Server**: **Vite 6**
- **Styling**: **Tailwind CSS 3.4**, modern dark/light glassmorphic UI, CSS modules for custom OCR tables
- **Icons & UI Primitives**: **Lucide React**, **Radix UI** primitives
- **Client Networking**: **Axios** (interceptors with automatic JWT bearer authorization)
- **Spreadsheet Generation**: **XLSX** (SheetJS) for client-side report exports

---

## 📍 Implementation Milestones: Till What Step We Have Reached

### ✅ Milestone 1: Multi-Tenant Client Management & Authentication
- User authentication with JWT access and refresh token rotation.
- Role-based authorization (`admin`, `ca`, `staff`, `client`).
- Client profile management with statutory fields: Legal Name, Trade Name, GSTIN, PAN, State Code, Contact Details, and **Return Frequency (`Monthly` vs `Quarterly`)**.

### ✅ Milestone 2: Multi-Tier OCR & Document Parsing Pipeline
- Ingestion supporting multi-page PDF, PNG, JPG, JPEG, WebP, TIFF, and scanned receipts.
- **Layered extraction**:
  1. Instant native PDF digital text extraction.
  2. High-resolution 300 DPI rendering for scanned documents.
  3. OpenCV adaptive thresholding and contrast optimization.
  4. Multi-PSM Tesseract OCR fallback for handwriting and structured tables.
- **Domain-Specific Document Parsers**:
  - **Tax Invoices & E-Invoices**: Invoice No, Date, Supplier/Recipient GSTINs, Taxable Value, CGST/SGST/IGST breakdown, Total Amount, QR Code / IRN deduplication.
  - **Credit & Debit Notes**: Note Number, Date, Reason, and `Against Invoice X dt Y` reference parsing.
  - **E-Way Bills (EWB)**: EWB No, Generated Date, Valid Until, Vehicle No, From/To locations.
  - **GST Challans**: CPIN (14-digit), CIN, Payment Date, Bank Name, Head-wise deposit breakdown.
  - **HSN/SAC Masters**: 4/6/8-digit HSN codes, descriptions, and statutory tax rates.
- **OCR Party Cleanups & Normalization**: Stripping OCR prefixes (e.g. `(From)`), filtering invalid party extractions (e.g. `Entered Date` on EWBs), and recipient auto-normalization.

### ✅ Milestone 3: Statutory Pre-Posting Validation Gate
- **Mathematical Parity**: `ROUNDING_TOLERANCE = 1.00` (₹1.00 tolerance per Section 170 CGST Act).
- **Zero Remainder Plug**: Discrepancies within ₹1.00 are systematically allocated to round-off rather than distorting tax heads.
- **Statutory Error Codes**:
  - `TOTAL_MISMATCH`: Line items or tax components do not equal gross total.
  - `TAX_TYPE_MISMATCH`: Intra-state supplies charging IGST, or inter-state charging CGST/SGST.
  - `GSTIN_FORMAT_INVALID`: Validates standard 15-character Indian GSTIN structure.
  - `CLIENT_MISMATCH`: Rejects documents where neither supplier nor recipient matches the active client's GSTIN.
  - `DUPLICATE`: Detects duplicate invoice numbers or duplicate e-invoices against existing bills.

### ✅ Milestone 4: Double-Entry Accounting Engine & Standard CoA
- **Standard Indian Chart of Accounts (4-Digit Standard)**:
  - `1000–1999`: Assets (1010 Sundry Debtors, 1020 Cash, 1030 Bank, 1210 Input CGST, 1220 Input SGST, 1230 Input IGST).
  - `2000–2999`: Liabilities (2010 Sundry Creditors, 2110 Output CGST, 2120 Output SGST, 2130 Output IGST).
  - `3000–3999`: Equity & Capital Accounts.
  - `4000–4999`: Revenue (4010 Domestic Sales, 4020 Inter-State Sales, 4030 Sales Returns).
  - `5000–5999`: Cost of Goods & Operating Expenses (5010 Purchases, 5020 Purchase Returns).
- **Statutory Double-Entry Mapping Templates (T1 to T6)**:
  - **T1 (Sales)**: `Dr Sundry Debtors` | `Cr Sales (4010/4020)` | `Cr Output CGST/SGST/IGST (2110/2120/2130)`
  - **T2 (Purchase)**: `Dr Purchases/Expenses (5010)` | `Dr Input CGST/SGST/IGST (1210/1220/1230)` | `Cr Sundry Creditors (2010)`
  - **T3 (Sales Credit Note)**: `Dr Sales Return (4030)` | `Dr Output CGST/SGST/IGST (2110/2120/2130)` | `Cr Sundry Debtors`
  - **T4 (Sales Debit Note)**: `Dr Sundry Debtors` | `Cr Sales (4010)` | `Cr Output CGST/SGST/IGST (2110/2120/2130)`
  - **T5 (Purchase Debit Note)**: `Dr Sundry Creditors` | `Cr Purchase Return (5020)` | `Cr Input CGST/SGST/IGST (1210/1220/1230)`
  - **T6 (Purchase Credit Note)**: `Dr Sundry Creditors` | `Cr Purchase Return (5020)` | `Cr Input CGST/SGST/IGST (1210/1220/1230)`
- **Automated Note Direction Anchor**: Credit/debit note direction is anchored to `client.gst_number`, linked original invoice lookup, explicit CA `applies_to` override (`sales` | `purchase`), and party role matching.
- **Strict Debits-First Ordering**: Vouchers enforce debits (`debit_amount > 0`) at lines 1, 2... followed by credits.

### ✅ Milestone 5: General Ledger, Trial Balance & Financial Statements
- Immutable journal entries with status workflow (`draft` -> `posted` -> `voided`/`reversed`).
- Account-wise General Ledger drill-down with running debit/credit balances.
- Real-time Trial Balance with automatic double-entry health verification (`Total Dr == Total Cr`).
- Profit & Loss Statement (Gross Profit, Operating Profit, Net Profit) and Balance Sheet (Assets vs Liabilities & Equity).

### ✅ Milestone 6: Statutory GST Module (C1–C12 Integrity Changes)
- **Single Source of Truth (R6 & C1)**: GSTR-1, GSTR-2B, and GSTR-3B derive figures **exclusively from posted General Ledger entries (`JournalEntryLine`)**. Unposted or draft documents can never pollute statutory figures.
- **GSTR-1 Statutory Classification (C4)**:
  - **B2B**: Registered recipient with valid GSTIN.
  - **B2C Large**: Unregistered inter-state supplies with invoice value **> ₹1,00,000** (reflecting statutory amendment Notification No. 12/2024-Central Tax).
  - **B2C Small**: Intra-state supplies to unregistered persons + inter-state supplies ≤ ₹1,00,000.
  - **CDNR / CDNUR**: Credit & Debit Notes (sales-side only, properly netted).
  - **HSN Table 12**: Summarized taxable turnover, tax rates, and tax heads grouped by HSN/SAC.
- **Purchase Register (ITC / GSTR-2B) (C5)**:
  - Aggregates exclusively inward vouchers (T2, T5, T6).
  - Validates Section 16(2) compliance (document existence, tax paid status, receipt verification).
- **GSTR-3B Statutory Tax Set-Off (Section 49) (C10)**:
  - Enforces mandatory statutory utilization order:
    1. **IGST Credit**: Exhausted first against IGST liability, then CGST liability, then SGST liability.
    2. **CGST Credit**: Utilized against CGST liability, then remaining IGST liability. *Cannot offset SGST.*
    3. **SGST Credit**: Utilized against SGST liability, then remaining IGST liability. *Cannot offset CGST.*
  - Formulates Table 6 Net Cash Payable per individual tax head (`IGST`, `CGST`, `SGST`).
  - Tracks excess Input Tax Credit carried forward to subsequent return periods.

### ✅ Milestone 7: Audit Protection, Period Control & Data Remediation
- **Document Deletion Guard (C8)**: System strictly blocks deletion of any source document linked to a posted `JournalEntry` or `AccountingRecord` (recommends reversing void instead).
- **Source Verification on Voucher Creation (C8)**: Requires verifiable document existence before voucher posting.
- **Accounting Period Lock (C9 & C11)**: Filing a return (`create_gst_record`) automatically locks the corresponding `AccountingPeriod`, preventing backdated entries into finalized periods.
- **Duplicate Filing Prevention (C11)**: Prevents duplicate return filings for the same client, return period, and form type.
- **System Audit Script**: [backend/scripts/integrity_check.py](backend/scripts/integrity_check.py) conducts automated read-only scans across:
  - Orphan vouchers (vouchers without source docs).
  - Unposted verified invoices.
  - Non-invoice document voucher isolation.
  - Double-entry mathematical equilibrium.
  - Ledger-to-GST return reconciliation.
- **Polluted Data Remediation Script**: [backend/scripts/cleanup_polluted_data.py](backend/scripts/cleanup_polluted_data.py) remediated historical test data on test client "Ankit public Ltd" via mirror reversals and voiding, bringing the database to **0 orphan vouchers**.

### ✅ Milestone 8: UI Workspace Integration & Micro-Polish
- **GST Workspace View**: Dedicated "Purchase Register (ITC)" tab, period selector dropdown (Monthly/Quarterly per client), B2C Large visibility, and pre-filled statutory return filing modal.
- **Voucher Detail Modal**: Displays tax rate percentages (e.g. `18%`, `9%`) alongside ledger accounts, and accurately labels account heads ("Trade Payables", "Duties & Taxes (asset)").
- **Client Workspace**: Seamless navigation between Invoices, Accounting Vouchers, General Ledger, Trial Balance, Financial Reports, and GST Portal Reconciliation.

---

## 🧪 Verification & Test Suite Status

The codebase is backed by **167 automated tests** covering unit logic, regression characterization, and statutory end-to-end acceptance pipelines.

```bash
backend/venv/Scripts/python.exe -m pytest backend/tests
```

```text
====================== 167 passed, 33 warnings in 7.75s =======================
Exit Code: 0
```

### Breakdown of Test Coverage:
| Test Suite | File | Tests | Focus |
|---|---|---|---|
| **Characterization Regression** | `test_characterization_regression.py` | 2 | Pins baseline voucher math, rounding tolerances, zero plug logic |
| **Statutory Acceptance Pipeline** | `test_statutory_acceptance_pipeline.py` | 5 | End-to-end statutory verification of Scenario A, Scenario B, and edge cases |
| **Audit & GST Hardening** | `test_audit_posting_and_gst_hardening.py` | 10 | Document deletion blocks, non-invoice isolation, period locking |
| **Journal Entry Engine** | `test_journal_entry_engine.py` | 15 | Double-entry equilibrium, debits-first ordering, voucher lifecycle |
| **General Ledger** | `test_general_ledger.py` | 23 | Account ledger drill-downs, running balances, date filtering |
| **Chart of Accounts** | `test_chart_of_accounts.py` | 22 | CoA seeding, hierarchy, parent-child groups, code uniqueness |
| **Voucher Management** | `test_voucher_management.py` | 20 | Voucher queries, draft editing, party sub-ledger tracking |
| **Financial Statements** | `test_financial_statements.py` | 25 | Profit & Loss math, Balance Sheet balancing, drill-downs |
| **Trial Balance** | `test_trial_balance.py` | 14 | Trial balance generation, group summaries, health checks |
| **OCR & Document Extraction** | `test_ocr_extraction.py` | 17 | OCR parsing, regex matching, party cleanups, non-invoice isolation |
| **Accounting Draft Bridge** | `test_accounting_draft_bridge.py` | 8 | Invoice-to-draft mapping, template assignment, status transitions |
| **GST Reconciliation** | `test_gst_reconciliation.py` | 6 | Return aggregation, GSTR-1 classification, GSTR-3B tax set-off |

### Frontend Production Build:
```bash
npm run build
```
```text
✓ 2411 modules transformed.
dist/index.html                     0.82 kB │ gzip:   0.46 kB
dist/assets/index-BD0uKEYx.css    130.14 kB │ gzip:  19.82 kB
dist/assets/xlsx-CkFp8p6R.js      429.53 kB │ gzip: 143.08 kB
dist/assets/index-BB0RUuVP.js   1,124.93 kB │ gzip: 312.83 kB
✓ built in 12.12s
Exit Code: 0
```

---

## 📂 Project Directory Structure

```text
FINAL YEAR CA FRONT/
├── backend/                              # FastAPI Backend Application
│   ├── alembic/                          # Alembic Database Migration Scripts
│   ├── app/
│   │   ├── api/                          # Route Handlers
│   │   │   ├── auth_router.py            # JWT Authentication & Registration
│   │   │   ├── client_router.py          # Client Profile Management
│   │   │   ├── invoice_router.py         # Document Ingestion, Guarded Deletion
│   │   │   └── routers/
│   │   │       ├── accounting/           # Vouchers, GL, Trial Balance, CoA Routers
│   │   │       ├── chatbot/              # Gemini AI Chatbot Router
│   │   │       ├── gst/                  # Statutory GST Return & Filing Router
│   │   │       ├── ocr/                  # Layered OCR & Domain Parsers (EWB, Challan, HSN)
│   │   │       ├── reports/              # P&L, Balance Sheet, Financial Reports Router
│   │   │       └── tax/                  # Income Tax & Computation Router
│   │   ├── core/                         # Core Settings (config.py, tolerances, thresholds)
│   │   ├── database/                     # SQLAlchemy Engine & SessionLocal
│   │   ├── models/                       # 10+ SQLAlchemy ORM Models
│   │   ├── repositories/                 # Data Access Layer
│   │   ├── schemas/                      # Pydantic Schemas for Requests & Responses
│   │   └── services/                     # Business Logic Services
│   │       ├── accounting_draft_service.py # Draft Voucher Preparation
│   │       ├── accounting_mapping_service.py # Templates T1-T6, Note Direction Anchor
│   │       ├── chart_of_accounts_service.py# Standard 4-Digit CoA Management
│   │       ├── financial_statements_service.py # P&L and Balance Sheet Engine
│   │       ├── general_ledger_service.py # GL Aggregation & Account Views
│   │       ├── gst_reconciliation_service.py # Single-Source-of-Truth GST Engine
│   │       ├── journal_entry_service.py  # Immutable Voucher Engine & Period Lock
│   │       └── trial_balance_service.py  # Trial Balance & Health Checks
│   ├── scripts/
│   │   ├── integrity_check.py            # Read-Only Database & Ledger Audit Tool
│   │   └── cleanup_polluted_data.py      # Standalone Ankit public Ltd Remediation
│   ├── tests/                            # 167 Pytest Suites
│   └── requirements.txt                  # Python Dependencies
├── datasets/                             # Test Documents, Sample Invoices, Categories
├── docs/
│   ├── CHANGES_PLAN.md                   # Architectural Plan for Statutory Changes C1–C12
│   └── CHANGES_REPORT.md                 # Complete Audit Report & Before/After Numbers
├── src/                                  # React Frontend Application Root
│   └── app/
│       ├── components/
│       │   ├── client/                   # Workspace, OCR Modals, GST & Voucher Views
│       │   ├── common/                   # Badges, Global Search, UI Primitives
│       │   └── layout/                   # Sidebar, Navigation, App Layout
│       ├── pages/                        # Dashboard, Workspace, Login, Assistant, Settings
│       └── services/                     # Axios API Services (Auth, Invoices, GST, GL)
├── .env.example                          # Environment Variables Template
├── .gitignore                            # Root Git Ignore Rules
├── package.json                          # Frontend Dependencies & Scripts
├── tsconfig.json                         # TypeScript Configuration
├── vite.config.ts                        # Vite Configuration & Dev Proxy
└── README.md                             # This Project Documentation
```

---

## ⚡ Quick Start & How to Run

### 1. Backend Setup
```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables in backend/.env
# DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/ca_assistant_db
# GEMINI_API_KEY=your_gemini_api_key

# Run the FastAPI server
uvicorn app.main:app --reload --port 8000
```
- API Documentation is live at: `http://localhost:8000/docs`

### 2. Frontend Setup
```bash
# From the project root
npm install

# Start the Vite development server
npm run dev
```
- Application UI is live at: `http://localhost:5173`

### 3. Run Automated Tests & Audits
```bash
# Run all backend tests
backend/venv/Scripts/python.exe -m pytest backend/tests -v

# Run the statutory system integrity audit script
backend/venv/Scripts/python.exe backend/scripts/integrity_check.py

# Verify frontend production build
npm run build
```

---

## 🔮 What's Next on the Roadmap

The statutory integrity and core accounting engine are complete. Future planned enhancements include:
1. **Section 17(5) Blocked ITC Automation**: Automated tagging of ineligible credit (motor vehicles, food/beverages, club memberships).
2. **Reverse Charge Mechanism (RCM)**: Self-invoicing and reciprocal liability accounting under Section 9(3)/9(4).
3. **Direct GSTN Portal Sync**: Automated GSTR-2B download and filing via GST Suvidha Provider (GSP) APIs.
4. **NIC E-Invoice Portal Verification**: Live QR code decoding and IRN authenticity checks against the IRP portal.
5. **Multi-Currency Support**: Foreign currency transactions with automated forex gain/loss posting.

---

<div align="center">
  <strong>FinLedger AI — Engineered for Mathematical Precision & Statutory Compliance</strong>
</div>