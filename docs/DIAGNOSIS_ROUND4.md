# Phase A — Round 4 Diagnosis & Status Audit Report (F1–F11 / X1–X9)

**Date:** 08-Oct-2026  
**Client Inspected:** C-1071 (`oggy pvt ltd`, GSTIN `27AABCA1234A1Z5`, Maharashtra, Quarterly)  
**Database:** PostgreSQL (`ca_assistant_db` on port 5432)  
**Branch:** `fix/gst-parity-round4`  

---

## 1. Explicit Answers to Phase A Questions (A1–A7)

### A1. Database URLs, Scripts, and Service Restarts
- **Backend Server:** Running via `uvicorn app.main:app --reload --port 8000` inside `backend/`. Its connection string is loaded from `backend/.env`:
  `DATABASE_URL=postgresql+psycopg://postgres:Bhumi%402005@localhost:5432/ca_assistant_db`
- **Pytest:** Runs against an isolated in-memory SQLite database (`sqlite:///:memory:`) in each test file to ensure test isolation.
- **Repair Scripts:** All scripts in `backend/scripts/` import `SessionLocal` from `app.database`, which resolves `DATABASE_URL` from `backend/.env`. Therefore, running backend and scripts use the **exact same PostgreSQL database**.
- **Were repair scripts run with `--apply` on C-1071?**
  **NO.** A dry-run inspection reveals:
  - `reextract_party_fields.py --dry-run --client-id 915b40bc-cfff-49e1-87ac-f79fa861c0e6` detected 2 documents needing party extraction (`E1` and `EWB1`), but was never run with `--apply`.
  - `cleanup_polluted_data.py` only had hardcoded references to Ankit client (`C-1070`) test vouchers (`NEG/0001`, `NEG/0002`). It did not target C-1071's bogus record.
  - `repost_legacy_vouchers.py` found voucher `PMT-2026-0001` but dry-run proposed the same lines because `PMT-2026-0001` is already a payment voucher.
- **Service Restarts:**
  - Running background processes: Uvicorn (FastAPI) on port 8000 and Vite dev server on port 5173. Uvicorn `--reload` watched files, but backend and frontend will be cleanly restarted and verified.

---

### A2. X1: CDNR vs CDNUR Note Classification
- **Code Path:** `backend/app/services/gst_reconciliation_service.py:448-461, 496`
- **Why S1 is B2B but CN1 is CDNUR:**
  - On `S1` (`b43c25ec`), `d.metadata_["fields"]["customer_gstin"]` contains `"27AAAPM5678B1Z2"`.
  - On `CN1` (`fb1ce894`), `d.gstin` is `"27AABCA1234A1Z5"` (the client's own supplier GSTIN) and `d.metadata_["fields"]` is empty `{}`.
  - In `gst_reconciliation_service.py:452`:
    ```python
    elif (doc_g and len(doc_g) == 15 and doc_g != client_gstin ...):
        recipient_gstin = doc_g
    ```
    Because `doc_g == client_gstin` (`27AABCA1234A1Z5 == 27AABCA1234A1Z5`), `doc_g != client_gstin` is `False`.
  - The service did not inspect the printed note text (`Recipient (To) Mehta Enterprises ... GSTIN: 27AAAPM5678B1Z2`) nor did it fall back to the referenced original invoice (`Against Invoice ABC/26-27/001 dt 05-Jul-2026`).
  - Thus `recipient_gstin` evaluated to empty `""`, and line 496 classified `CN1` as `CDNUR` with Party GSTIN empty ("Unregistered").
- **Voucher / Journal Header:**
  - `JournalEntry` currently lacks `counterparty_name` and `counterparty_gstin` columns.
  - Vouchers rely entirely on looking up source documents. Additive columns on `JournalEntry` (`counterparty_name`, `counterparty_gstin`) will allow storing and reading authoritative counterparty GST data directly.

---

### A3. X2: Filing Records Creation Paths
- **Code Paths:**
  1. Frontend: `src/app/components/client/GstWorkspaceView.tsx:368-391` allowed users to type `filingTaxable` (e.g. `90000000.00`) and `filingTax` (`0.00`).
  2. Backend: `backend/app/api/routers/gst/router.py:288-315` (`create_gst_record`):
     ```python
     if taxable_amount is None or taxable_amount == Decimal("0.00"):
         # Only server-derives if None or 0!
     ```
     Because the payload contained non-zero taxable `90,000,000.00`, the server accepted free-typed figures without server computation.
  3. No period-ended check: The endpoint never validated `period_end < today`. Period `2026-10` ends on `2026-10-31`, while the record was posted on `2026-10-05`.
  4. No return frequency check: Client C-1071 has `return_frequency = 'Quarterly'`, but the endpoint accepted monthly period string `2026-10`.
  5. The resulting record `e89e205d-f826-4728-92ef-09714fedc6ad` (`2026-10 | GSTR-3B | taxable 9,00,00,000 | tax 0 | filed`) has no backing ledger transactions.

---

### A4. X3: Counterparty on Client-Issued Purchase Notes (PDN1)
- **Code Path:**
  1. Voucher generation: `backend/app/services/accounting_draft_service.py:271`:
     ```python
     elif category == "debit_note":
         party_label = doc.vendor or "Vendor"
     ```
     For PDN1 (debit note issued by client to supplier), OCR recorded issuer (ABC Traders Pvt Ltd) as `vendor` and recipient (TN Raw Materials Ltd) as `customer`.
     Because `accounting_draft_service.py` naively took `doc.vendor`, it set `party_label = "ABC Traders Pvt Ltd"`.
  2. Sub-ledger line / AccountingRecord: `AccountingRecord.description` was populated with `"Ref: ABC/PDN/26-27/001 | Party: ABC Traders Pvt Ltd | ..."`.
  3. Purchase register: `backend/app/services/gst_reconciliation_service.py:781-782`:
     ```python
     party_name = d.vendor or d.customer
     party_gstin = d.gstin
     ```
     `d.vendor` is `"ABC Traders Pvt Ltd"` and `d.gstin` is `"27AABCA1234A1Z5"`.
- **Root Cause:** The code assumed `d.vendor` is always the counterparty. For a client-issued purchase debit note, the client is the issuer/vendor and the supplier is the recipient (`d.customer`). The counterparty must always be the side whose GSTIN is **not** the client's GSTIN (`TN Raw Materials Ltd` / `33AABCT1111E1Z6`).

---

### A5. X4 / X5: Duplicate Invoices & E-Invoice Linking
- **Duplicate Detection & Tax at Risk:**
  - `backend/app/services/gst_reconciliation_service.py:1321`:
    ```python
    variance_amount = tot_amt,  # GROSS AMOUNT! (118,000 instead of 18,000)
    ```
    This violated Rule R5 (tax at risk must be tax amount, never gross).
  - Both duplicate S1 (`3c3ecc9e`) and companion e-invoice E1 (`3785d117`) raised `UNPOSTED_INVOICE` because line 1270 included `e_invoice` in `unposted_eligible_categories` and did not verify whether a linked/companion invoice is already posted.
  - Duplicate detection did not set `doc.status = "rejected"` with `rejection_reason = "DUPLICATE"`.
- **E-Invoice Numbering & Linking:**
  - `backend/app/api/routers/ocr/router.py:2818`: `_parse_e_invoice` called `_parse_invoice`. The 64-character IRN hash matched first, storing the IRN into `invoice_number` instead of the printed `Document No: ABC/26-27/002`.
  - Linking in `DocumentDetailModal.tsx:1615` listed all documents without ranking by number, party, or direction, leading to mis-linking.

---

### A6. X6: Second HIGH Discrepancy under "All Available"
- **Finding:** Under `period=None` ("All Available"), `detect_discrepancies` returns **4 issues (2 HIGH, 2 MEDIUM)**:
  1. `[MEDIUM] UNPOSTED_INVOICE` on duplicate S1 (`3c3ecc9e-b7dd-4c97-be94-27ebab6bccfb`, ₹18,000).
  2. `[HIGH] DUPLICATE_INVOICE` on duplicate S1 (`3c3ecc9e-b7dd-4c97-be94-27ebab6bccfb`, ₹1,18,000 -> tax at risk bug).
  3. `[MEDIUM] UNPOSTED_INVOICE` on e-invoice E1 (`3785d117-2d2a-4131-b584-d169cb09f034`, ₹36,000).
  4. **`[HIGH] LEGACY_VOUCHER_NO_TAX_LINES`** on voucher `PMT-2026-0001` (entry ID `edc852f0-e8bf-4afc-b610-062472a47ca2`, doc `bf9154a5-0347-4dd9-9d4d-47077ce7fce4`, `GST_Challan_Q2.pdf`, ref `26100012345678`), **variance amount ₹84,700.00**!
- **Is it legitimate?**
  **NO, IT IS A FALSE POSITIVE.**
  - `PMT-2026-0001` is a statutory **Payment Voucher** for paying GST via Challan dated `2026-10-20`.
  - Its double-entry lines are: `Dr 2150 GST Tax Payment Clearing Account (84,700) | Cr 1020 Main Bank Current Account (84,700)`.
  - Payment vouchers clear tax clearing liabilities. They do **not** have output/input GST lines (they are not sales/purchase vouchers).
  - In `detect_discrepancies` (lines 1362-1395), `je.entry_type == "payment"` was NOT excluded!
  - Under `period='2026-Q2'` (July to September 2026), `PMT-2026-0001` was excluded by date (`2026-10-20` is Q3).
  - But under `period=None` ("All Available"), there was no date filter, so Check 6 evaluated `PMT-2026-0001`, saw document tax ₹84,700, saw no lines on accounts 2110/2120/2130/1210/1220/1230, and fired a false HIGH alert `LEGACY_VOUCHER_NO_TAX_LINES`!
  - **Resolution (F8/F9):** Exclude payment vouchers (and non T1-T6 vouchers) from `LEGACY_VOUCHER_NO_TAX_LINES`, and flag `PMT-2026-0001` with `FUTURE_DATED_PAYMENT` (MEDIUM, non-blocking) if its date is after today.

---

### A7. X7: HSN Table 12 under "All Available" vs Q2
- **Why Table 12 was empty under "All Available":**
  - Line 1673 in `backend/app/services/gst_reconciliation_service.py`:
    ```python
    if not raw_items and d.file_path and os.path.exists(d.file_path):
    ```
  - `os` was **never imported** at module scope in `gst_reconciliation_service.py`!
  - When line 1673 executed for any document lacking metadata line items, Python raised:
    `NameError: name 'os' is not defined`.
  - The uncaught exception caused the API to fail or return an empty dataset to the frontend ("0 Classified Codes").
- **What it returns once `os` is imported (verified live):**
  Exactly 3 rows, matching Table 3.1:
  1. `4820 | Notebooks and stationery | 5.00% | 20,000.00 | 1,000.00 | 1 voucher`
  2. `9401 | Office Chair (ergonomic) | 18.00% | 80,000.00 | 14,400.00 | 2 vouchers`
  3. `998314 | Software development services | 18.00% | 200,000.00 | 36,000.00 | 1 voucher`
  - Total Taxable: ₹300,000.00 | Total Tax: ₹51,400.00.
  - Under `period=None` ("All Available") and `period='2026-Q2'`, the data is identical.

---

## 2. Status Audit Matrix (E1–E11 & F1–F11)

| Item | Description | (a) Implemented in Code? (File:Line) | (b) Covered by Test? | (c) Applied to Live DB? | (d) Visible in Live UI? | Status / Action Needed |
|---|---|---|---|---|---|---|
| **E1 / F-base** | GSTR-3B Cash 35,200 & Reversal 1,800 | `gst_reconciliation_service.py:1020-1090` | Yes (`test_gst_parity_round3_e2e.py`) | Yes (dynamic) | Yes (35,200 cash, 1,800 reversal) | **ALREADY CORRECT** — Preserved intact |
| **E2 / F7** | HSN Table 12 Outward Sales Only | `gst_reconciliation_service.py:1600-1760` | Yes (`test_hsn_table_12_sales_only.py`) | Crash in DB call (`NameError: os`) | "0 Classified Codes" | **Fix F7**: Add `import os`, strict T1/T3/T4 filter, no empty table on All Available |
| **E3 / F1** | Note CDNR vs CDNUR Classification | `gst_reconciliation_service.py:448-496` | Partial | No (CN1 missing customer_gstin) | Shows CDNUR "Unregistered" | **Implement F1**: Recipient GSTIN from note / parent inv; add voucher counterparty cols; backfill |
| **E4 / F3** | Bogus Filing Records | `cleanup_polluted_data.py` (Ankit only) | No | No (record `e89e205d` active) | Shows `2026-10 / 9,00,00,000 / Filed` | **Implement F3**: `void_bogus_filings.py`, server-authoritative endpoint, quarterly range |
| **E5 / F5** | E-Invoice / EWB Doc No & Auto-Link | `ocr/router.py:2818` (used IRN) | No | No (E1 inv_no is IRN, E1->S3, EWB1->P1) | UNPOSTED alert, wrong links | **Implement F5**: Extract Document No to `invoice_number`, add `irn` field, number-first link script |
| **E6 / F2** | Counterparty on Client Notes (PDN1) | `accounting_draft_service.py:271` | No | No (JV-2026-0002 has client as party) | Purchase register shows client name | **Implement F2**: Counterparty = non-client GSTIN; SELF_PARTY gate; reverse-repost PDN1 |
| **E7 / F8** | Payment Voucher GST Isolation | `gst_reconciliation_service.py:1362-1408` | No | No (PMT voucher raises LEGACY alert) | Modal has tax labels; alert on All Avail | **Implement F8**: Exclude payment vouchers from tax discrepancy; "Amount paid" modal labels; FUTURE_DATED_PAYMENT |
| **E8 / F4** | Discrepancies & Duplicate Handling | `gst_reconciliation_service.py:1321` | No | No (Duplicate tax at risk = 118,000) | 1,18,000 gross shown, duplicate verified | **Implement F4**: Tax at risk = tax only; mark duplicate rejected; exclude compliance docs from unposted |
| **E9 / F6** | Filing Dialog Constraints | `GstWorkspaceView.tsx:325-390` | Partial | No | Pre-fills 2026-09 on All Available | **Implement F6**: Block All Available; show quarter label; read-only computed figures |
| **E10 / F11** | Account 4020 Sales Return Contra-Rev | `chart_of_accounts_service.py` | Yes | Yes (role `SALES_RETURN`) | Yes | Contra-revenue verified |
| **E11 / F11** | Governance Counters | `GstWorkspaceView.tsx:247-260` | No | No (Filed counts voided, Verified counts dup) | Filed=1 on All Avail, Verified=11 | **Implement F11**: Exclude voided from Filed, exclude rejected from Verified, Posted=7 |
| **E-Wording / F10**| Table 4 ITC Wording | `GstWorkspaceView.tsx:645-660` | No | N/A | "100% of inward tax is claimable" | **Implement F10**: True breakdown: "ITC available 18,000, reversed 1,800, net 16,200" |
