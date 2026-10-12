# FinLedger AI — Government Rule Engine (`/app/updates`) Design & Architecture

**Date:** 2026-10-12  
**Module:** Government Statutory Rule Engine (`/app/updates`)  
**Status:** In Production  
**Backend Port:** `8000` | **Frontend Port:** `5173`

---

## 1. Executive Summary & Objective

The **Government Rule Engine** is the statutory intelligence module of FinLedger AI. It ingests, normalizes, indexes, and explains real statutory circulars, notifications, advisories, and gazettes published by Indian official public bodies (CBIC, GST Council, Income Tax Department, RBI, ICAI, NFRA, and the e-Gazette of India).

### Core Principles & Compliance Mandates
1. **Zero Simulated Data (R1):** The database and UI only contain genuine government publications. When empty or un-synced, an honest empty state (`"No updates synced yet"`) is presented. No hardcoded cards, synthetic dates, or fake thresholds are allowed.
2. **Statutory Integrity & Legal Hierarchy (R7):** Press releases and advisories are deterministically classified as `press_release_not_law` or `advisory` and never presented as operative legal instruments. Circulars and notifications reference their governing Act (e.g., distinguishing between the new *Income-tax Act, 2025* and the historic *Income-tax Act, 1961*).
3. **Polite, Ethical Crawler (R5, R6):** Strict adherence to `robots.txt`, domain rate-limiting (min 3.0s per host), conditional GETs (`If-Modified-Since`, `ETag`), 20s network timeout, 15MB file ceiling, SSRF domain allowlists, and immediate respectful backoff upon encountering WAF challenges or CAPTCHAs.
4. **Hard-Grounded AI Explanations (R8):** AI summaries must pass an entity and numerical grounding audit. If the summary mentions numbers, percentages, or dates not verbatim in the source statutory text, it is rejected and safely replaced with a deterministic statutory excerpt.
5. **System Isolation (R2, R3):** Gov Updates tables (`gov_sources`, `gov_updates`, `gov_fetch_runs`, `gov_saved_updates`) are strictly isolated. All other modules (clients, accounting, GST, invoices, auth) remain completely untouched.

---

## 2. Architecture & Data Flow

```
   ┌─────────────────────────────────────────────────────────────┐
   │            Official Government Public Sources               │
   │  RBI RSS | GST Council HTML | ICAI HTML | e-Gazette HTML    │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │      Polite HTTP Client (app.services.gov_updates.client)    │
   │  - User-Agent: FinLedgerBot/1.0 (+compliance@finledger.ai)   │
   │  - robots.txt Parser & In-Memory TTL Cache                  │
   │  - Per-Host Rate Limiter (Token Bucket / min 3.0s delay)     │
   │  - SSRF Allowlist & Header-Based Challenge Detector         │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │         Adapters (app.services.gov_updates.adapters)        │
   │  - RssAdapter: Parses XML/Atom feed items                   │
   │  - HtmlListingAdapter: Parses table & list DOM structures   │
   │  - PdfExtractor: pypdf streaming text extraction (15MB cap) │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │      Deterministic Normalizer (gov_updates.normalizer)      │
   │  - Legal Status Tagging (press_release vs operative)        │
   │  - Law Version Disambiguation (2025 vs 1961 vs CGST 2017)   │
   │  - Fixed Topics Taxonomy (rates, itc, e_invoicing, etc.)    │
   │  - Supersession Reference Regex Extraction                  │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │        AI Explainer with Hard Grounding Check (J6)          │
   │  - Verifies all numbers, percentages, and dates exist in txt│
   │  - Rejects hallucinations -> fallback to excerpt            │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │              PostgreSQL Database Persistence                 │
   │  - gov_sources (17 registered, 6 enabled)                   │
   │  - gov_updates (indexed by doc_number, hash, issue_date)    │
   │  - gov_fetch_runs (audit logging of every scrape cycle)     │
   │  - gov_saved_updates (per-user bookmarks isolation)         │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                 FastAPI REST API (/api/v1/gov-updates)       │
   │  - GET / (facets, filters, search, pagination, bookmarking) │
   │  - GET /{id} (statutory detail + citations)                 │
   │  - GET /meta (counts, sync times, source health stats)      │
   │  - GET /sources (live status, health, toggle)               │
   │  - POST /sync (on-demand synchronization)                   │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │          React Frontend Interface (src/app/pages/GovRules)   │
   │  - Header Stats Banner (Operative Laws, Active Sources)     │
   │  - Statutory Classification Badges & Legal Warnings         │
   │  - Detail Drawer with Copy Citation & PDF Deep Link         │
   │  - Sources Health Status Popover                            │
   └─────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema

All tables created via idempotent Alembic migration `0011_add_gov_updates_tables.py`:

### Table: `gov_sources`
Tracks configured statutory authorities, their crawler method, polling frequency, and operational health.
```sql
CREATE TABLE gov_sources (
    id UUID PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    tier INTEGER NOT NULL DEFAULT 1,
    method VARCHAR(50) NOT NULL, -- 'rss' | 'html_listing' | 'api'
    poll_frequency_mins INTEGER NOT NULL DEFAULT 60,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(50) NOT NULL DEFAULT 'ok', -- 'ok' | 'degraded' | 'blocked_requires_verification' | 'disabled'
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Table: `gov_updates`
Stores individual statutory circulars, notifications, advisories, and gazettes.
```sql
CREATE TABLE gov_updates (
    id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES gov_sources(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    doc_type VARCHAR(50) NOT NULL, -- 'circular' | 'notification' | 'order' | 'advisory' | 'press_release' | 'gazette'
    legal_status VARCHAR(50) NOT NULL DEFAULT 'operative_instrument', -- 'operative_instrument' | 'advisory' | 'press_release_not_law' | 'clarification_only' | 'proposed_amendment'
    doc_number VARCHAR(100),
    issue_date DATE,
    effective_date DATE,
    category VARCHAR(50) NOT NULL, -- 'GST' | 'INCOME_TAX' | 'TDS' | 'BUDGET' | 'CORPORATE_LAW' | 'ACCOUNTING_STANDARDS' | 'BANKING' | 'OTHER'
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    law_version VARCHAR(100), -- 'CGST Act 2017' | 'Income-tax Act, 2025' | 'Income-tax Act, 1961' | 'Companies Act 2013'
    url VARCHAR(1000) NOT NULL,
    pdf_url VARCHAR(1000),
    content_text TEXT,
    text_status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'ok' | 'no_text' | 'scanned_pdf' | 'failed'
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active', -- 'active' | 'superseded' | 'withdrawn' | 'repealed'
    status_confidence FLOAT NOT NULL DEFAULT 1.0,
    supersedes_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    ai_summary TEXT,
    ai_status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'done' | 'skipped' | 'failed'
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    backfilled BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_gov_update_content UNIQUE(source_id, content_hash)
);
```

### Table: `gov_fetch_runs`
Audit log recording every execution of the crawler for complete compliance trace.
```sql
CREATE TABLE gov_fetch_runs (
    id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES gov_sources(id) ON DELETE CASCADE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL DEFAULT 'running', -- 'running' | 'success' | 'failed' | 'partial' | 'blocked'
    items_new INTEGER NOT NULL DEFAULT 0,
    items_updated INTEGER NOT NULL DEFAULT 0,
    items_skipped INTEGER NOT NULL DEFAULT 0,
    http_status INTEGER,
    error_message TEXT
);
```

### Table: `gov_saved_updates`
Tenant-isolated bookmarks saving user preferences.
```sql
CREATE TABLE gov_saved_updates (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    update_id UUID NOT NULL REFERENCES gov_updates(id) ON DELETE CASCADE,
    saved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_gov_saved_user_update UNIQUE(user_id, update_id)
);
```

---

## 4. Source Registry & How to Add a New Source

### 4.1. Configured Registry
Defined in `app.services.gov_updates.registry.GOV_SOURCES_REGISTRY`. 17 sources configured:
1. `rbi_notifications`: Reserve Bank of India Notifications (RSS, Enabled)
2. `rbi_pressreleases`: Reserve Bank of India Press Releases (RSS, Enabled)
3. `gstcouncil`: Goods & Services Tax Council Recommendations (HTML, Enabled)
4. `icai_announcements`: Institute of Chartered Accountants of India (HTML, Enabled)
5. `egazette_recent`: Official Gazette of India Extraordinary (HTML, Enabled)
6. `nfra_orders`: National Financial Reporting Authority Orders (HTML, Enabled)
7. `cbic_gst`: CBIC Central Board of Indirect Taxes (HTML, Disabled pending NIC gateway)
8. `cbic_taxinfo`: CBIC Tax Information Publisher (HTML, Disabled pending NIC gateway)
9. `gstn_news`: GST Portal Updates (HTML, Disabled - WAF 403 Challenge)
10. `incometax_feed`: Income Tax Department Updates (RSS, Disabled - WAF 403 Challenge)
11. `pib_rss`: PIB Finance Ministry Feed (RSS, Disabled - WAF 403 Challenge)
12. `dor`: Department of Revenue (HTML, Disabled pending gateway)
13. `finmin`: Ministry of Finance (HTML, Disabled pending gateway)
14. `indiabudget`: Union Budget of India (HTML, Disabled - WAF 403 Challenge)
15. `mca`: Ministry of Corporate Affairs (HTML, Disabled - WAF 403 Challenge)
16. `sebi_circulars`: SEBI Circulars (HTML, Disabled)
17. `mahagst`: Maharashtra State GST (HTML, Disabled)

### 4.2. Step-by-Step: Adding a New Official Source
1. **Probe the Source Endpoint:**
   Verify `robots.txt` and HTTP status using curl or python:
   ```bash
   curl -I -A "FinLedgerBot/1.0 (+compliance@finledger.ai)" https://example.gov.in/circulars
   ```
2. **Add Domain to SSRF Allowlist:**
   In `app/services/gov_updates/client.py`, add the authority domain to `ALLOWED_GOV_DOMAINS`.
3. **Register Source in Registry:**
   In `app/services/gov_updates/registry.py`, append entry to `GOV_SOURCES_REGISTRY`:
   ```python
   {
       "code": "new_source_code",
       "name": "Authority Full Name",
       "base_url": "https://newsource.gov.in",
       "domain": "newsource.gov.in",
       "tier": 1,
       "method": "html_listing",  # or 'rss'
       "poll_frequency_mins": 120,
       "enabled": True,
       "status": "ok",
   }
   ```
4. **Implement Parsing Logic:**
   - If RSS/Atom: standard `RssAdapter` handles it automatically.
   - If HTML: Add extraction selector in `app/services/gov_updates/adapters/html_adapter.py` matching the portal's DOM table or news list structure.
5. **Add Fixture & Unit Test:**
   - Save sample response HTML/XML to `backend/tests/fixtures/gov/new_source/sample.html`.
   - Add parsing assertion in `backend/tests/test_gov_updates_module.py`.
6. **Apply Seed & Test Ingestion:**
   Run `seed_gov_sources(db)` and run sync via `GovSyncEngine.sync_source(db, source)`.

---

## 5. Polite Crawler & Ethical Rules Enforcement

FinLedger strictly obeys the rules of ethical web crawling:
- **`User-Agent` Header:** Strictly declared as `FinLedgerBot/1.0 (+compliance@finledger.ai)`.
- **`robots.txt` Verification:** Checked on every request. Disallowed paths immediately abort fetch with an audit log. Cached for 1 hour.
- **Domain Token Bucket Rate Limiting:** Enforces minimum 3.0s delay between requests to the same hostname, with clock-injection support for deterministic testing.
- **WAF / CAPTCHA Policy (R6):** Never attempts to solve CAPTCHAs, emulate headless stealth browsers, or bypass cloud WAFs. If HTTP 403 or challenge headers (Cloudflare, Akamai, NIC Challenge) are received, the crawler immediately sets `status = "blocked_requires_verification"` and disables automated polling.
- **SSRF Allowlist:** Network requests are strictly restricted to `.gov.in`, `.nic.in`, `.icai.org`, and verified statutory domains. RFC 1918 private IPs (`10.0.0.0/8`, `192.168.0.0/16`, `127.0.0.1`) are blocked at URL resolution.
- **Download Limits:** Response stream terminates if size exceeds 15MB. Network timeout capped at 20.0s.

---

## 6. Deterministic Normalizer & Statutory Classification

Statutory accuracy is enforced before database persistence:
1. **Legal Status Taxonomy:**
   - `operative_instrument`: Statutory circulars, notifications, gazettes with legal force.
   - `advisory`: Technical notes or GST portal advisories.
   - `press_release_not_law`: PIB and Ministry press releases. **Must never be treated as legal law.**
   - `clarification_only`: FAQs and procedural clarifications.
2. **Law Versioning (2025 vs 1961 Act):**
   - Income tax rules notifying or referencing the *Income-tax Act, 2025* are explicitly tagged `law_version = "Income-tax Act, 2025"`.
   - References to the *Income-tax Act, 1961* are preserved with `law_version = "Income-tax Act, 1961"`.
   - GST items tagged `law_version = "CGST Act 2017"`.
3. **Supersession Reference Tracking:**
   Regex pattern `(?:supersedes|in supersession of|amends|withdrawn)[\s\w]*?(circular\s+no\.?\s*[\w\/-]+|notification\s+no\.?\s*[\w\/-]+)` extracts superseded statutory numbers and marks previous records in the database with status `superseded`.
4. **Fixed Topic Taxonomy:**
   Items are mapped exclusively to controlled taxonomy tags (`rates`, `exemption`, `itc`, `e_invoicing`, `returns_filing`, `registration`, `assessment_appeal`, `penalties_interest`, `transfer_pricing`, `audit_standards`, `banking_regulations`, `other`). Unrecognized tags are disallowed.

---

## 7. AI Explainer & Anti-Hallucination Grounding

AI summaries are powered by `app.services.gov_updates.ai_explainer`:
- Uses Google Gemini `gemini-2.5-flash` model.
- **Hard Grounding Verification:** `verify_grounding(summary_text, source_content)`:
  - Extracts all numerical tokens, percentages (`5%`, `18%`), currency amounts (`₹5 Cr`), and dates (`18 Jul 2026`).
  - Checks if every extracted entity exists verbatim in the source statutory text.
  - If any number is ungrounded (e.g., hallucinating a threshold that does not exist in the circular), the summary is discarded and replaced with a deterministic statutory excerpt.

---

## 8. Verification & Test Suite Summary

- **Total Unit & Integration Tests:** 285 tests (264 existing + 21 Government Updates tests) passing with 0 errors.
- **Frontend Build:** `npm run build` verified cleanly (0 TypeScript errors).
- **Live Database Integrity:** Baseline counts across business tables verified identical before and after (`clients: 52`, `documents: 65`, `uploaded_documents: 57`, `journal_entries: 21`).
- **Live Ingested Statutory Records:** 61 authentic records actively indexed from RBI, GST Council, ICAI, e-Gazette, and NFRA.
