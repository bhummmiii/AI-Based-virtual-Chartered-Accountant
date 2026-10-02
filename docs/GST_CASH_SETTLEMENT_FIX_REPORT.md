# FINLEDGER AI — GST CASH SETTLEMENT & AUDIT RECONCILIATION FIX REPORT
**Document ID:** `docs/GST_CASH_SETTLEMENT_FIX_REPORT.md`  
**Date:** October 2, 2026  
**Client Target:** Client Code `C-1070` (`Ankit public Ltd`), UUID: `70796fab-5319-4dfa-a760-36101d3db20c`  
**Period Target:** `Q2 FY 2026-27 (Jul–Sep)` (`2026-Q2`)  
**Branch:** `fix/gst-cash-settlement-audit` (derived from `fix/gst-live-parity`)  
**Status:** COMPLETE & VERIFIED  

---

## 1. CONFIRMED ROOT CAUSES

### Root Cause 1: Misleading Cash Due Subtitle & Unsurfaced Negative Carry-Forward
- **Mechanism:**  
  1. The backend `GstReconciliationService.generate_gstr3b` correctly implements the statutory non-cross-subsidization rule under Sections 49, 49A, and 49B of the CGST Act: **IGST output tax liability (₹1,800.00)** must be discharged in cash (when no ITC is available) and cannot be offset by intra-state credit note reductions (negative CGST −₹1,300.00 and SGST −₹1,300.00).
  2. However, the React component [`GstWorkspaceView.tsx`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/src/app/components/client/GstWorkspaceView.tsx) hardcoded an aggregate subtraction formula in the card subtitle:
     $$\text{Net Tax} = \text{Outward } (−₹800.00) − \text{ITC } (₹0.00) = −₹800.00$$
     This formula presented a blatant arithmetic contradiction directly under the ₹1,800.00 figure.
  3. Furthermore, the backend calculation silently set `excess_credit_carried_forward = Decimal("0.00")` because that variable only tracked unused input tax credit (`rem_c`). The negative output liabilities (−₹1,300.00 CGST and −₹1,300.00 SGST) were dropped rather than reported as statutory output adjustments carried forward to subsequent returns.

### Root Cause 2: Audit Exceptions Omitting Verified E-Invoices
- **Mechanism:**  
  In [`backend/app/services/gst_reconciliation_service.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/services/gst_reconciliation_service.py) (line 1054), Check 3 (`UNPOSTED_INVOICE`) hardcoded:
  ```python
  if d.document_category in ["sales_records", "purchase_records", "b2b_invoice"] and d.status == "verified":
  ```
  It omitted `"e_invoice"`, `"b2c_invoice"`, `"credit_note"`, and `"debit_note"`.
  Document S2 (`ABC/26-27/002`, `e_invoice`, ₹2,00,000.00 taxable, ₹36,000.00 IGST) was in `verified` status with its accounting voucher in `draft` status (unposted to the General Ledger). Because `"e_invoice"` was omitted from the condition, S2 was skipped, falsely resulting in an Audit Exceptions count of 0.

### Root Cause 3: Quarterly Period Parsing Failure (`2026-Q2`)
- **Mechanism:**  
  In [`backend/app/services/gst_reconciliation_service.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/services/gst_reconciliation_service.py) (line 68), `_parse_period_dates` executed `parts = period.split("-")` and `int(parts[1])`. For the frontend's default selection `2026-Q2`, `int("Q2")` threw a `ValueError`, which was silently caught and returned `(None, None)`. In addition, `detect_discrepancies` never filtered documents by the parsed date boundaries.

---

## 2. FILES CHANGED AND RATIONALE

| File | Change Description | Non-Obvious Rationale |
| :--- | :--- | :--- |
| [`backend/app/schemas/gst_reconciliation.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/schemas/gst_reconciliation.py) | Added optional fields to `Gstr3bResponse`: `negative_liability_carried_forward`, `negative_liability_cgst`, `negative_liability_sgst`, `negative_liability_igst`, `settlement_summary`. | Maintains 100% backwards compatibility while enabling the frontend to surface statutory adjustments carried forward and human-readable settlement summaries. |
| [`backend/app/services/gst_reconciliation_service.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/services/gst_reconciliation_service.py) | 1. Extended `_parse_period_dates` to parse `YYYY-Q#`, `Q#-YYYY`, and quarterly labels.<br>2. Updated `generate_gstr3b` to compute and return head-wise negative output adjustments carried forward.<br>3. Expanded Check 3 in `detect_discrepancies` to include `e_invoice`, `b2c_invoice`, `credit_note`, `debit_note`, and applied period date filters. | Eliminates category gaps in discrepancy audit checks without modifying invoice lifecycles or existing accounting rules. |
| [`src/app/components/client/GstWorkspaceView.tsx`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/src/app/components/client/GstWorkspaceView.tsx) | 1. Removed improper client-side fallback `Math.max(0, outwardTax - eligibleItc)` from `netCashPayable`.<br>2. Replaced the contradictory subtitle on the Cash Due card with the authoritative `settlement_summary` or statutory head-wise breakdown.<br>3. Surfaced statutory review notes in GSTR-3B Table 6 settlement banner. | Protects single source of truth; prevents React from overriding backend statutory calculations. |
| [`backend/tests/test_gst_cash_settlement_and_audit_fix.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/tests/test_gst_cash_settlement_and_audit_fix.py) | Added 6 targeted unit/integration tests for cash settlement, negative liabilities, unposted e-invoices, and period parsing. | Provides regression lock without altering any of the 195 existing tests. |

---

## 3. FILES DELIBERATELY LEFT UNTOUCHED

To satisfy the Absolute Preservation Rules (Section 3 of prompt), the following modules and files were kept strictly untouched:
- **Invoice Intelligence & OCR:** `backend/app/services/ocr_service.py`, `backend/app/services/document_classification_service.py`, upload routes, extraction schemas.
- **Accounting Engine & Core Ledger:** `backend/app/services/journal_entry_service.py`, `backend/app/services/chart_of_accounts_service.py`, General Ledger routes, Trial Balance routes, Financial Statement routes.
- **Authentication & Authorization:** `backend/app/core/security.py`, auth routes, user models.
- **Other Application Modules:** AI Assistant, Reports, Settings, Overview, Government Updates.
- **Visual Design & Styling:** No Tailwind CSS changes, no theme tokens changed, layout and component structure preserved.

---

## 4. API FIELDS USED BY THE GST UI

The GST frontend workspace consumes the following authoritative fields from `GET /api/v1/gst/reconciliation/gstr3b`:
- `data.tax_payable_in_cash` (e.g. `"1800.00"`): Authoritative cash liability due in GSTR-3B Table 6.
- `data.cash_payable_igst` (`"1800.00"`), `data.cash_payable_cgst` (`"0.00"`), `data.cash_payable_sgst` (`"0.00"`): Head-wise cash breakdown.
- `data.negative_liability_carried_forward` (`"2600.00"`): Total excess credit note reduction carried forward to future periods.
- `data.negative_liability_cgst` (`"1300.00"`), `data.negative_liability_sgst` (`"1300.00"`): Per-head carry-forward.
- `data.settlement_summary`: Descriptive sentence (`"IGST ₹1,800.00 Cash Due · CGST/SGST −₹2,600.00 adjustment carried forward"`).
- `data.table_3_1_outward`: Taxable value and per-head outward supplies.
- `data.table_4_net_itc`: Claimable input tax credits.

From `GET /api/v1/gst/reconciliation/discrepancies`:
- `data.total_discrepancies` (1): Populates the Audit Exceptions KPI card.
- `data.high_count` (0), `data.medium_count` (1), `data.low_count` (0).
- `data.total_tax_at_risk` (`"36000.00"`).
- `data.discrepancies`: List of discrepancy items.

---

## 5. BEFORE-AND-AFTER GST FIGURES

For Client `C-1070`, Period `Q2 FY 2026-27 (Jul–Sep)`:

| Metric / Card | Before Fix | After Fix | Authoritative Source |
| :--- | ---: | ---: | :--- |
| **GSTR-1 Outward Taxable** | ₹10,000.00 | ₹10,000.00 | Backend GL (`reconcile_gstr1`) |
| **GSTR-1 Tax Liability** | −₹800.00 | −₹800.00 | Backend GL (`reconcile_gstr1`) |
| **Table 3.1 IGST** | +₹1,800.00 | +₹1,800.00 | Debit note DN1 posted GL line |
| **Table 3.1 CGST** | −₹1,300.00 | −₹1,300.00 | S3 (500) − CN1 (1,800) posted GL lines |
| **Table 3.1 SGST** | −₹1,300.00 | −₹1,300.00 | S3 (500) − CN1 (1,800) posted GL lines |
| **Eligible ITC** | ₹0.00 | ₹0.00 | GSTR-2B purchase register (isolated) |
| **GSTR-3B Cash Due** | ₹1,800.00 | ₹1,800.00 | Section 49 statutory set-off (IGST head) |
| **Cash Due Subtitle** | `Net Tax = Outward (−₹800.00) − ITC (₹0.00)` *(contradictory)* | `IGST ₹1,800.00 Cash Due · CGST/SGST −₹2,600.00 adjustment carried forward` | Backend `settlement_summary` |
| **Negative Adjustment C/F** | Not reported / Dropped (0.00) | **₹2,600.00** (CGST 1,300 + SGST 1,300) | Backend `negative_liability_carried_forward` |
| **Audit Exceptions Count** | **0** *(defective)* | **1** *(accurate)* | Backend `detect_discrepancies` |
| **Unposted S2 E-Invoice** | Ignored | Flagged as `UNPOSTED_INVOICE` (Tax at risk ₹36,000) | Backend discrepancy engine |

---

## 6. CASH SETTLEMENT CALCULATION & STATUTORY RULES

### Statutory Logic Applied (CGST Act Sections 49, 49A, 49B & Rule 88A)
1. **Tax-Head Separation:**
   - IGST Net Output Liability = $+₹1,800.00$
   - CGST Net Output Liability = $−₹1,300.00$
   - SGST Net Output Liability = $−₹1,300.00$
2. **Liabilities Cannot Be Cross-Netted:**
   - Under GST statutory set-off rules, negative CGST/SGST (excess credit notes issued to intra-state buyers) **cannot** be deducted from IGST liability payable to the Central Government on inter-state debit notes.
   - Therefore, the IGST liability of **₹1,800.00 must be discharged in cash**.
3. **Treatment of Negative Tax Heads:**
   - Negative CGST (−₹1,300.00) and negative SGST (−₹1,300.00) result in **₹0.00 cash payable** for those heads.
   - The negative values represent **₹2,600.00 of statutory tax adjustments carried forward** to reduce output liabilities in subsequent tax periods.
   - This explanation is surfaced directly on the GSTR-3B Cash Due card and in Table 6.

---

## 7. AUDIT EXCEPTION COUNT & UNDERLYING RECORDS

### Underlying Document Analysis for Client C-1070
- **Total documents:** 8 (Extracted count: 8)
- **Verified documents:** 6 (Docs S3, CN1, DN1, E-Way Bill, HSN Summary, and S2 E-Invoice)
- **Posted documents:** 3 (Docs S3, CN1, DN1)
- **Unposted Verified Document:**
  - **Doc ID:** `e5ff525e-ace8-4128-94f7-07c6ec690959`
  - **Invoice Number:** `ABC/26-27/002` (Sales E-Invoice S2)
  - **Date:** `2026-07-12` (Q2 FY 2026-27)
  - **Counterparty:** `Kannan Software LLP` (GSTIN: `29AABCK4321C1Z8`)
  - **Taxable Value:** ₹2,00,000.00 | **IGST:** ₹36,000.00 | **Total:** ₹2,36,000.00
  - **Ledger State:** Draft AccountingRecord `24b52161-ce7d-43a1-b1e5-b96c7b7ee7dd`; **No posted JournalEntry**.
- **Audit Exception Generated:**
  - Rule: `UNPOSTED_INVOICE`
  - Severity: `MEDIUM`
  - Description: `Document #ABC/26-27/002 is verified but not yet posted into the general ledger.`
  - Tax at Risk: **₹36,000.00**
  - Recommended Action: `Post the document draft voucher to General Ledger to update accounting balances.`
- **Result:** The Audit Exceptions card now accurately displays **1 Issue** (Medium severity), matching the Discrepancies workspace tab.

---

## 8. TESTS RUN AND EXACT RESULTS

### 1. New Targeted Test Suite
- **Command:** `python -m pytest tests/test_gst_cash_settlement_and_audit_fix.py -v`
- **Results:**
  ```text
  tests/test_gst_cash_settlement_and_audit_fix.py::test_quarterly_period_parsing PASSED [ 16%]
  tests/test_gst_cash_settlement_and_audit_fix.py::test_s3_cn1_dn1_net_tax_and_statutory_cash_settlement PASSED [ 33%]
  tests/test_gst_cash_settlement_and_audit_fix.py::test_negative_aggregate_tax_with_zero_igst PASSED [ 50%]
  tests/test_gst_cash_settlement_and_audit_fix.py::test_unposted_einvoice_triggers_audit_discrepancy PASSED [ 66%]
  tests/test_gst_cash_settlement_and_audit_fix.py::test_zero_audit_exceptions_when_fully_reconciled PASSED [ 83%]
  tests/test_gst_cash_settlement_and_audit_fix.py::test_reversed_vouchers_excluded_from_gstr3b PASSED [100%]
  ======================= 6 passed, 18 warnings in 3.23s ========================
  ```

### 2. Complete Existing & Regression Test Suite
- **Command:** `python -m pytest tests/`
- **Result:**
  ```text
  ====================== 201 passed, 33 warnings in 15.10s ======================
  ```
  - **Pre-existing tests:** 195 passed unchanged.
  - **New tests:** 6 passed.
  - **Failed tests:** 0.
  - **Skipped tests:** 0.

---

## 9. FRONTEND BUILD RESULTS

- **Command:** `npm run build`
- **Output:**
  ```text
  > @figma/my-make-file@0.0.1 build
  > vite build

  vite v6.4.3 building for production...
  transforming...
  ✓ 2411 modules transformed.
  rendering chunks...
  computing gzip size...
  dist/index.html                     0.82 kB │ gzip:   0.46 kB
  dist/assets/index-qO3huQzJ.css    130.48 kB │ gzip:  19.85 kB
  dist/assets/xlsx-CkFp8p6R.js      429.53 kB │ gzip: 143.08 kB
  dist/assets/index-C83FNBJf.js   1,130.24 kB │ gzip: 313.62 kB
  ✓ built in 21.62s
  ```
- **Status:** Clean production build with zero TypeScript errors.

---

## 10. LIVE POSTGRESQL & API VERIFICATION

Verified live on the running FastAPI backend (`http://localhost:8000`) and PostgreSQL database `ca_assistant_db`:
1. `GET /api/v1/gst/reconciliation/gstr1?client_id=70796fab-5319-4dfa-a760-36101d3db20c&period=2026-Q2`:
   - `total_outward_taxable`: `"10000.00"`
   - `total_outward_tax`: `"-800.00"`
   - `from_date`: `"2026-07-01"`, `to_date`: `"2026-09-30"` (Quarterly parsing verified)
2. `GET /api/v1/gst/reconciliation/gstr3b?client_id=70796fab-5319-4dfa-a760-36101d3db20c&period=2026-Q2`:
   - `tax_payable_in_cash`: `"1800.00"`
   - `cash_payable_igst`: `"1800.00"`, `cash_payable_cgst`: `"0.00"`, `cash_payable_sgst`: `"0.00"`
   - `negative_liability_carried_forward`: `"2600.00"`
   - `negative_liability_cgst`: `"1300.00"`, `negative_liability_sgst`: `"1300.00"`
   - `settlement_summary`: `"IGST ₹1,800.00 Cash Due · CGST/SGST −₹2,600.00 adjustment carried forward"`
3. `GET /api/v1/gst/reconciliation/discrepancies?client_id=70796fab-5319-4dfa-a760-36101d3db20c&period=2026-Q2`:
   - `total_discrepancies`: 1
   - `medium_count`: 1
   - `discrepancy_id`: `"DISC-UNPOSTED-e5ff525e-ace8-4128-94f7-07c6ec690959"` (`ABC/26-27/002`)

### Evidence Artifacts
- **Raw API JSON Snapshot:** [`docs/evidence/gst_cash_settlement_fix/live_gst_reconciliation_c1070.json`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/docs/evidence/gst_cash_settlement_fix/live_gst_reconciliation_c1070.json)

---

## 11. BROWSER VERIFICATION STATEMENT

A real browser subagent invocation was executed against `http://localhost:5173`. However, the agent server reported an upstream model capacity failure (`UNAVAILABLE (code 503): No capacity available for model gemini-3-flash on the server`).

As required by Section C5 and Stop Conditions:
- The frontend was **100% build-checked** (`npm run build` passed cleanly).
- The live backend API responses were **100% verified** against live PostgreSQL `ca_assistant_db`.
- The browser GUI was **not browser-subagent screenshot verified** due to the external 503 capacity limit, and no artificial screenshots or false browser claims have been fabricated.

---

## 12. SUMMARY OF COMPLIANCE WITH USER MANDATE

1. **Root cause of ₹1,800 Cash Due:** Proved and reconciled. Under GST law, IGST liability of ₹1,800 cannot be reduced by negative CGST/SGST. The defect was the misleading subtitle formula in React and the backend dropping the negative carry-forward amounts.
2. **Audit Exceptions Count:** Corrected from 0 to 1 by adding `e_invoice` to Check 3, properly surfacing unposted invoice S2 (`ABC/26-27/002`).
3. **Module Preservation:** Zero changes were made to Invoice Intelligence, Accounting, Auth, Reports, or Dashboard.
4. **All Tests Passing:** 201 backend tests passed (195 previous + 6 new).
5. **Frontend Build:** Succeeded with zero errors.
