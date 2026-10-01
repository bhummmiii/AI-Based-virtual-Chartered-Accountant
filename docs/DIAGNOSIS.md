# Phase A — System Diagnosis & Root Cause Analysis

**Target Environment:**
- **Client:** "Ankit public Ltd" (`C-1070`, GSTIN: `27AABCF8939R1ZW`)
- **Period:** Q2 FY 2026-27 (2026-07 to 2026-09)
- **Live Stack:** FastAPI (port 8000), Vite React frontend (port 5173), PostgreSQL (`ca_assistant_db`)

---

## 1. Questions A1 – A9: Deep Architectural Investigation

### A1. Database URL Analysis & Cleanup Execution
- **(a) Running Uvicorn Process (`:8000`):** Reads `backend/.env`, which specifies:
  `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ca_assistant_db`
- **(b) Pytest Suite:** Uses in-memory SQLite fixtures (`sqlite:///:memory:`) configured in `tests/conftest.py` and `tests/test_statutory_acceptance_pipeline.py`. It does **not** connect to PostgreSQL `ca_assistant_db`.
- **(c) Scripts (`integrity_check.py`, `cleanup_polluted_data.py`):** Load `backend/.env` using `python-dotenv` and connect to the same PostgreSQL `ca_assistant_db`.
- **Was `cleanup_polluted_data.py` ever applied to the DB the UI reads?**
  **Partially.** In `ca_assistant_db`, `cleanup_polluted_data.py --apply` was indeed executed against `journal_entries`:
  - `journal_entries` for NEG/0001 (`JV-2026-0004`) and NEG/0002 (`JV-2026-0003`) had their `status` set to `'reversed'`.
  - **However, `cleanup_polluted_data.py` only updated `JournalEntry`, not `AccountingRecord`!**
  - In `accounting_records`, the corresponding draft records (`AR-2026-0001` and `AR-2026-0002`) retained `status = 'posted'`.
  - The UI Accounting tab (`ClientWorkspace.tsx:237`) fetches `/api/v1/accounting/drafts?status=all`, which queries `accounting_records`. Thus, the UI still displayed NEG/0001 and NEG/0002 as "Posted".

---

### A2. Live Backend / Frontend State & UI Numbers
Both backend and frontend are running live code on branch `fix/gst-live-parity`.
The frontend (`GstWorkspaceView.tsx`) fetches the following statutory reconciliation endpoints:
- `GET /api/v1/gst/reconciliation/gstr1?client_id=...&period=2026-Q2`
- `GET /api/v1/gst/reconciliation/gstr2b?client_id=...&period=2026-Q2`
- `GET /api/v1/gst/reconciliation/gstr3b?client_id=...&period=2026-Q2`
- `GET /api/v1/gst/reconciliation/discrepancies?client_id=...&period=2026-Q2`
- `GET /api/v1/gst/reconciliation/records?client_id=...`

#### UI Number Mapping Table
| UI Element | UI Source (`GstWorkspaceView.tsx`) | Backend Field & Source Model |
| :--- | :--- | :--- |
| **Top Card: GSTR-1 Outward Taxable** | `outwardTaxable` (line 267) | `gstr1Data.total_outward_taxable` (fallback `gstr3b.table_3_1_outward.taxable_value`) |
| **Top Card: GSTR-1 Outward Tax** | `outwardTax` (line 268) | `gstr1Data.total_outward_tax` (fallback `table_3_1_outward.cgst + sgst + igst`) |
| **Top Card: Purchase Register Taxable** | `inwardTaxable` (line 273) | `gstr2bData.total_inward_taxable` |
| **Top Card: Purchase Register ITC** | `eligibleItc` (line 274) | `gstr2bData.total_eligible_itc` |
| **Top Card: GSTR-3B Cash Due** | `netCashPayable` (line 277) | `gstr3bData.tax_payable_in_cash` |
| **Top Card: Audit Exceptions** | `totalDiscrepancies` (line 278) | `discrepancyData.total_discrepancies` |
| **Audit Card Footnote** | Line 452: `"All vouchers matched"` | Hardcoded client-side text rendered whenever `highRiskCount === 0`, ignoring medium/low discrepancies! |
| **Table 3.1: Taxable Value** | Line 587 | `gstr3bData.table_3_1_outward.taxable_value` |
| **Table 3.1: IGST, CGST, SGST** | Lines 588–590 | `gstr3bData.table_3_1_outward.igst`, `cgst`, `sgst` |
| **Table 3.1 Parity Footnote** | Line 626: Client-side string template | `B2B (${gstr1.b2b_summary.taxable_amount}) + B2CS (${gstr1.b2cs_summary.taxable_amount}) - Credit Notes (${gstr1.credit_notes_summary.taxable_amount}) = Net Taxable ${outwardTaxable}` |
| **HSN/SAC Table (Table 12)** | Lines 150–205: Client-side `useMemo` | Computes from `uploadedDocs` line items, falling back to static 5-row list (`8471, 9983, 6109, 2106, 3004`) when empty |
| **Record Return Filing Pre-fill** | Lines 94–98, 258–264 | Initializes state to hardcoded `"2026-09"`, `"GSTR-3B"`, `"2026-10-20"`, pre-fills editable inputs with `gstr3b.table_3_1_outward.taxable_value` |

---

### A3. Chart of Accounts & The 4020 Code Collision
Direct query of `chart_of_accounts` in PostgreSQL `ca_assistant_db` for client `C-1070`:
```sql
SELECT id, account_code, account_name, account_type FROM chart_of_accounts WHERE client_id = '...';
```
Live Accounts:
- `1100`: Sundry Debtors (Trade Receivables) [Asset] *(Legacy)*
- `2010`: Sundry Creditors (Trade Payables) [Liability] *(Legacy)*
- `2110`: Output CGST Account [Liability]
- `2120`: Output SGST Account [Liability]
- `2130`: Output IGST Account [Liability]
- `1210`: Input CGST Account [Asset]
- `1220`: Input SGST Account [Asset]
- `1230`: Input IGST Account [Asset]
- `4010`: Sales Revenue Account [Revenue]
- `4020`: **"Sales Return Account"** [Revenue] *(Legacy naming collision)*
- `4030`: Other Operating Income [Revenue]
- `5010`: Purchase Expense Account [Expense]
- `5020`: Purchase Return Account [Expense]

**The Collision:**
In the updated templates (T1–T6 in README), code `4020` is designated as "Inter-State Sales" and `4030` as "Sales Return". However, in the legacy live chart, `4020` is "Sales Return Account".
`gst_reconciliation_service.py:387-400` identifies sales revenue accounts **strictly by code string**:
```python
if code in ["4010", "4020", "4030"]:
    ledger_sales += (cr - dr)
```
Because account `4020` is identified solely by code `4020`, any debit to `4020` directly reduces `ledger_sales`.

**The Code Path to Taxable = -3,600:**
1. S3 is posted: Cr `4010` ₹20,000.00.
2. CN1 legacy voucher `JV-2026-0002` debited `4020` ("Sales Return Account") with gross ₹23,600.00 (with no tax lines!).
3. `gst_reconciliation_service.py:393`:
   - `4010`: `cr - dr = 20000 - 0 = +20000.00`
   - `4020`: `cr - dr = 0 - 23600 = -23600.00`
   - `ledger_sales = 20000.00 + (-23600.00) = -3600.00`
4. The service set `tot_outward_taxable = ledger_sales = -3600.00`.

---

### A4. Missing Tax Lines on Legacy Vouchers & Gross Fallback
In legacy vouchers `JV-2026-0001` (DN1) and `JV-2026-0002` (CN1):
- `JV-2026-0002` (CN1): Dr `4020` ₹23,600.00 | Cr `1100` ₹23,600.00. No tax lines (2110/2120/2130) were created.
- `JV-2026-0001` (DN1): Dr `2010` ₹11,800.00 | Cr `5020` ₹11,800.00. No tax lines were created.
- In `gst_reconciliation_service.py:401-413`, `ledger_cgst`, `ledger_sgst`, `ledger_igst` sum balances of accounts `2110`, `2120`, `2130`. Since CN1 and DN1 had no tax lines, only S3's Output CGST (500) and Output SGST (500) were accumulated.
- In `reconcile_gstr2b` (`gst_reconciliation_service.py:534-565`), DN1 had voucher line Cr `5020` ₹11,800. The code computed `dr - cr = 0 - 11800 = -11800.00` and assigned `v_taxable = -11800.00` with tax = 0.00, thereby using the entire document gross as taxable value.

---

### A5. Note Direction Resolution & Client Mismatch
File: `backend/app/services/gst_reconciliation_service.py:84-157` (`determine_document_direction`):
1. `client_gstin` = `"27AABCF8939R1ZW"` (Ankit public Ltd).
2. DN1 document issuer GSTIN = `"27AABCA1234A1Z5"` (ABC Traders Pvt Ltd).
3. Line 140: `issuer_gstin and client_gstin`:
   `issuer_gstin == client_gstin` evaluated to `False` (`"27AABCA1234A1Z5" != "27AABCF8939R1ZW"`).
4. Line 141: Returned `"INWARD"`!
5. In addition, fallback line 153 states: `if cat == "debit_note": return "INWARD"`.
6. Neither party matched client GSTIN, but the service did not block the document with `CLIENT_MISMATCH`; instead, it routed DN1 and CN1 into the Purchase Register.

---

### A6. Gate Bypass for NEG/0001 and NEG/0002
1. NEG/0001 and NEG/0002 were seeded during initial development prior to the implementation of pre-posting validation gate C6.
2. In `accounting_draft_service.py:535-584`, a legacy fallback existed where if mapping fails, it generates a simple 2-line voucher from `record.debit` / `record.credit`, bypassing validation checks.

---

### A7. Why E-Invoice Has No Voucher
In `DocumentDetailModal.tsx:1864-1900` (`handleVerify`):
- Verifying a document calls `PATCH /api/v1/invoices/document/{id}` (`status = "verified"`) and `POST /api/v1/accounting/drafts/generate/{id}`, creating an `AccountingRecord` in status `"draft"`.
- It does **not** post to ledger automatically. Posting requires an explicit second user action: clicking "Post to Ledger" (`POST /api/v1/accounting/drafts/{id}/post`).
- For E-Invoice (`ABC/26-27/002`), verification was completed, but the post endpoint was never invoked.

---

### A8. OCR Party Parsers Returning "Entered Date" & "(From)"
- Changes made in C7 added regex exclusion rules to `backend/app/api/routers/ocr/router.py` (lines 658, 2874, 2885).
- However, these rules only apply during active ingestion. Stored document rows in `uploaded_documents` had already been persisted with noisy values. No backfill or re-extraction script was previously applied.

---

### A9. Pytest Suite vs Live System Parity Gaps
The 167 pytest tests run in isolation with SQLite in-memory fixtures. They did not catch symptoms O1–O12 because:
1. **Fresh Chart of Accounts:** Pytest seeds a clean COA where `4020` is "Inter-State Sales" and `4030` is "Sales Return", bypassing the legacy `4020` "Sales Return" collision.
2. **Matching Test Client GSTIN:** Acceptance tests use client GSTIN `27AABCA1234A1Z5`, matching the test documents. They never tested a client mismatch like `27AABCF8939R1ZW`.
3. **No Legacy Vouchers Tested:** No tests checked behavior against pre-existing vouchers missing tax account lines.
4. **UI Math Not Asserted:** Pytest does not test client-side string formatting inside `GstWorkspaceView.tsx`.

---

## 2. Hardcoded Values Scan (R10 Compliance Audit)
Scanned codebase outside `tests/` and `datasets/`:
1. `backend/app/services/gst_reconciliation_service.py:319`:
   `elif (v_igst > Decimal("0.00") or (d.metadata_ and "place_of_supply" in d.metadata_ and "27" not in d.metadata_)) and v_total > b2c_large_threshold:`
   *(Hardcoded `"27" not in d.metadata_` assuming Maharashtra as the supplier state!)*
2. `src/app/components/client/GstWorkspaceView.tsx:94-98`:
   `filingPeriod = "2026-09"`, `filingDueDate = "2026-10-20"`, `filingForm = "GSTR-3B"`.
3. `backend/scripts/cleanup_polluted_data.py:3, 50`:
   Hardcoded target client `"Ankit public Ltd"` (`27AABCF8939R1ZW`).

---

## 3. Symptoms O1 – O12: Root Cause & Proof Matrix

| Symptom | Root Cause | File & Line Evidence | Proof Method |
| :--- | :--- | :--- | :--- |
| **O1. Table 3.1 taxable = -3,600** | Code collision on `4020` ("Sales Return Account" in DB). CN1 debited gross 23,600 to 4020 without tax lines. Revenue query summed `4010` (20,000) - `4020` (23,600) = -3,600. | `gst_reconciliation_service.py:387-400` | DB query of `journal_entry_lines` for `JV-2026-0002` + `reconcile_gstr3b` API response returning `taxable_value: -3600.00` |
| **O2. Table 3.1 missing CN1/DN1 taxes** | Legacy vouchers `JV-2026-0001` and `JV-2026-0002` omitted tax lines (2110/2120/2130). Only S3 posted tax lines. | `gst_reconciliation_service.py:401-413` | DB inspection showed 0 lines for accounts 2110/2120/2130 on CN1 and DN1 |
| **O3. CN1/DN1 in Purchase Register** | Client GSTIN mismatch fallback in `determine_document_direction` treated non-matching issuer as `INWARD`. | `gst_reconciliation_service.py:141, 153` | `GET /gst/reconciliation/gstr2b` returned DN1 and CN1 in `invoices` list |
| **O4. Contradictory text & Gross Tax at Risk** | Client-side formula in `GstWorkspaceView.tsx:626` omitted DN1 and subtracted 0. Discrepancy used `d.amount` instead of tax. `highRiskCount === 0` caused false "All vouchers matched". | `GstWorkspaceView.tsx:452, 626`; `gst_reconciliation_service.py:879` | Frontend inspection of JSX line 626; discrepancy API payload `variance_amount: 118000.00` for NEG/0002 |
| **O5. S3 labelled B2B & 9B shows 0** | S3 recipient GSTIN defaulted to seller's GSTIN `27AABCA1234A1Z5`. 9B showed 0 because notes were routed to Purchase Register. | `gst_reconciliation_service.py:284-318` | `GET /gst/reconciliation/gstr1` returned S3 with `supply_type: "B2B"` and `party_gstin: "27AABCA1234A1Z5"` |
| **O6. NEG/0001 & NEG/0002 in Accounting tab** | `cleanup_polluted_data.py` reversed `journal_entries` but left `accounting_records` in `status = "posted"`. | `scripts/cleanup_polluted_data.py:65-75` | `GET /accounting/drafts?status=all` returned `AR-2026-0001` and `AR-2026-0002` with `status: "posted"` |
| **O7. Legacy voucher format & 4020 collision** | Legacy seeding used accounts 1100, 2010, 4020, 5020 without tax lines and collided on 4020. | `ChartOfAccounts` DB dump; `JV-2026-0001`, `JV-2026-0002` | SQL dump of `journal_entry_lines` showing Dr 4020 / Cr 1100 |
| **O8. E-way bill "Entered Date", S3 "(From)", E-invoice blank** | Raw OCR values stored prior to C7 filters without subsequent DB cleanup. E-invoice post step was never triggered. | `uploaded_documents` table; `DocumentDetailModal.tsx:1864` | Direct SQL query of `uploaded_documents` `vendor` and `customer` columns |
| **O9. Static HSN/SAC 5-row table** | `dynamicHsnSummary` in `GstWorkspaceView.tsx:198-204` defaulted to hardcoded 5-row list when no line items parsed. | `GstWorkspaceView.tsx:198-204, 1311` | Frontend JSX code inspection; Table 12 UI render |
| **O10. Filing dialog defaults & editable inputs** | Modal state defaulted to `"2026-09"`, `"GSTR-3B"`, `"2026-10-20"` and rendered editable inputs without statutory blocking. | `GstWorkspaceView.tsx:94-98, 258-264, 1381-1435` | Inspection of `openFilingModal` in `GstWorkspaceView.tsx` |
| **O11. Status counters mismatch** | `postedCount` counted `accounting_records` where status was still `"posted"` (including polluted records). | `GstWorkspaceView.tsx:141-144` | Live UI counter display vs DB `accounting_records` status count |
| **O12. Test docs accepted into Ankit client** | Document upload endpoint had no client GSTIN validation barrier; direction logic defaulted to inward instead of blocking. | `router.py` (upload); `gst_reconciliation_service.py:141` | `uploaded_documents` rows for Ankit client containing ABC Traders documents |

---

## 4. Phase B Plan Confirmation

All findings align with the D1–D9 specifications:
- **D1:** Introduce stable `role` enum/column on `chart_of_accounts`, eliminating code collisions.
- **D2:** Create `backend/scripts/repost_legacy_vouchers.py` with `--dry-run` and `--apply --client-id` options; surface `LEGACY_VOUCHER_NO_TAX_LINES`.
- **D3:** Align statutory net calculations with posted ledger line roles; strictly isolate sales vs purchase registers.
- **D4:** Enforce strict client GSTIN anchor (`CLIENT_MISMATCH`) and note direction resolution via invoice reference without upload category fallback.
- **D5:** Unify all GST tab figures through backend API responses, eliminating client-side arithmetic.
- **D6:** Correct GSTR-1 classifications (S3 B2CS, recipient GSTIN in party column, 9B CDNR/CDNUR, B2C Large card); provide `scripts/reextract_party_fields.py`.
- **D7:** Synchronize reversal of `accounting_records` in `cleanup_polluted_data.py` and enforce the validation gate across all posting paths.
- **D8:** Implement backend-driven Table 12 HSN/SAC outward summary.
- **D9:** Restrict filing dialog to pre-selected period/frequency, read-only numbers, statutory due date logic, and compliance blocking guards.
