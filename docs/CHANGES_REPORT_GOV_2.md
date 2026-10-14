# FinLedger AI — Government Updates Correction Round 2 Report (`docs/CHANGES_REPORT_GOV_2.md`)

**Date:** 2026-10-14  
**Module:** Government Statutory Rule Engine (`/app/updates`, page "Government Rule Engine")  
**Branch:** `fix/gov-updates-quality`  
**Engineer:** Senior Full-Stack Engineer  
**Status:** COMPLETE — All Items K1 through K13 Implemented and Verified on Live Stack  

---

## 1. Executive Summary & Verification

This correction round addressed items **K1 through K13** on the live stack for the "Government Updates" module (`/app/updates`), ensuring zero regressions across all other modules (`clients`, `invoices`, `accounting`, `GST`, `reports`, `auth`).

### Baseline Database Table Counts (R1 Invariant Verified)
Before and after this correction round, live database row counts were confirmed identical:
- `clients`: **52**
- `documents`: **65**
- `uploaded_documents`: **57**
- `journal_entries`: **21**
Zero rows were inserted, deleted, or modified in any business table outside `gov_*`. Pre-migration backup was created at `backend/backups/ca_assistant_db_pre_gov_quality.dump`.

---

## 2. Summary of Implemented Items (K1 – K13)

### K1: Source Status Model & Health Lifecycle
- **Model:** Defined authoritative statuses (`ok`, `degraded`, `blocked_requires_verification`, `unreachable`, `disabled`) with explicit transitions in `app/services/gov_updates/status_manager.py`.
- **Cool-Down:** Enforced 24-hour cool-down for blocked/unreachable sources (`next_retry_at = now + 24h`).
- **Header Counts:** Live header dynamically computes: `"Last successful sync hh:mm — 17 sources: 7 ok / 0 degraded / 5 blocked / 5 unreachable / 0 disabled"`. The counts partition mutually exclusively and sum to exactly 17.
- **Drawer Grid:** Operational metrics in Sources drawer display Last Attempt, Last Success, Failures / Stage, and Next Retry. Red error text is shown strictly when a source is degraded, blocked, or unreachable.

### K2: Real Statutory Endpoints & Owner Diagnostic Protocol
- **Endpoints:** Real target URLs integrated into `SOURCE_FETCH_ENDPOINTS` in `sync_engine.py`.
- **Documentation:** `docs/GOV_DIAGNOSIS_2.md` Section 2.1 documents root causes (bot-block WAF 403 vs network timeout vs site-down) and legitimate CA/owner next steps without CAPTCHA/WAF bypass (R5/R6).

### K3: Deterministic Issue Dates & Precision
- **Precision:** Added `date_precision` (`day` | `month` | `none`) and `issue_date_source`.
- **Rules:** Never guess day `01`. Meeting dates verified against official schedules (57th meeting = `2026-10-08`, 56th meeting = `2025-09-03`). Newsletters tagged with `month` precision. Stripped deadline phrases ("till 11.10.2025").
- **UI:** Month-precision dates render as "Oct 2026" / "Dec 2025"; NULL dates display "Date not stated".

### K4: Genuine Document Numbers & Provenance
- **Provenance:** Removed `#GSTC-57TH` synthesis and URL query extraction (`RBI-ID-`, `PR-`).
- **Verbatim Check:** In `normalizer.py`, `doc_number` MUST occur as a verbatim substring in `title` or `content_text`; otherwise `doc_number = None`. Card rendering removes `#` prefix and displays doc numbers cleanly in monospace pills.

### K5: Administrative Items & Legal Status Classification
- **Administrative Detection:** Keyword rules over title and text identify vacancies, exams, tenders, awards, and newsletters.
- **Filtering:** Administrative items are assigned `administrative_not_law`, have `hidden = True`, and are hidden behind the `show_administrative` toggle.
- **Legal Status:** Restricted `operative_instrument` strictly to statutory authorities issuing enforceable law. Chips consistently formatted in Title Case ("Operative", "Press Release — Not Law", "Administrative").

### K6: e-Gazette Ministry Filtering & Item-Specific Links
- **Allowlist:** e-Gazette parser filters strictly to tax/accounting ministries (`Ministry of Finance`, `Corporate Affairs`, `Law and Justice`, `NFRA`). Irrelevant ministries (Railways, Defence) hidden.
- **Direct Links:** Direct PDF links enforced; listing-only URLs flagged with `link_quality = "listing_only"` and labelled "Official source (listing)".

### K7: Text Quality Scoring & Letter-Spaced Text Repair
- **Scoring Engine:** Created `app/services/gov_updates/text_quality.py` with `score_text_quality` and `repair_letter_spaced_text`.
- **Repair:** Successfully repaired letter-spaced text in the GST Council December 2025 newsletter (`M E S S A G E   T h e   F i f t h` -> `MESSAGE The Fifth`), reducing single-char ratio from 1.0 to 0.07.
- **Anti-Hallucination:** Guarded AI prompts against misinterpreting "Extraordinary" in Extraordinary Gazette, and cleared AI summaries for unreadable items.

### K8: 14-Day "New" Badge Rule & Backfill
- **14-Day Rule:** `is_new` evaluates True ONLY when: `issue_date` is known AND `issue_date` is within 14 days AND `first_seen_at` is within 14 days AND `backfilled = false`.
- **Backfill:** All baseline items and undated items marked `backfilled = true`. Undated items are never marked "New".

### K9: Category Empty States & Coverage Clarity
- **Honest Banners:** Tabs for categories without active `ok` sources (Income Tax, Budget) render a dedicated banner: `"No source is currently available for <category> — <n> source(s) blocked or unreachable"`, listing unavailable sources and failure stages with shortcuts to manual import and sources drawer.

### K10: Manual Circular Import (CA / Admin)
- **Modal & Endpoint:** Built `ManualImportModal.tsx` and `POST /api/v1/gov-updates/manual-import`.
- **Security & Validation:** Enforces official domain allowlist (.gov.in, .nic.in, rbi.org.in, icai.org, sebi.gov.in, nfra.gov.in), 15MB file size limit, pypdf text extraction, SHA-256 deduplication, and audit logging in `GovFetchRun`.

### K11: Additional Working Sources & Documented Exclusions
- **Working Candidates:** Integrated `icai_idtc` (`idtc.icai.org`, HTTP 200) and `gstat` (`gstat.gov.in`, HTTP 200).
- **Excluded Sources:** Documented why Supreme Court / e-Courts, ITAT, TRACES, and e-filing are not integrated due to CAPTCHA/login restrictions per R5/R6.

### K12: Data Repair Script
- **Script:** Created `backend/scripts/repair_gov_updates.py` (dry-run default, `--apply` flag).
- **Application:** Applied repairs to 78 database rows without any deletions:
  - Corrected meeting dates (57th = 2026-10-08, 56th = 2025-09-03).
  - Nulled 18 synthetic document numbers.
  - Reclassified and hid administrative items.
  - Hid 4 non-allowlisted e-Gazette rows (Railways, Defence).
  - Backfilled 67 historical rows.

### K13: Test Suite, Verification & Evidence Export
- **Backend Tests:** 290 passed in 29.64s (`pytest tests/`). Full coverage for K1–K12 rules with SQLite in-memory isolation.
- **Frontend Build:** `npm run build` completed cleanly with 0 TypeScript/esbuild errors.
- **Evidence:** Exported JSON payloads, baseline counts, and spot-check documentation to `docs/evidence_gov_updates_2/`.

---

## 3. Git Commits Log on `fix/gov-updates-quality`
- `a9b45f8`: K1: Implement source status model, cool-down, header counts and reset script
- `77a093a`: K2: Real statutory endpoints integration and diagnostic documentation
- Pending Commit: K3-K13 implementation across backend and frontend, test suite enhancements, and evidence artifacts.
