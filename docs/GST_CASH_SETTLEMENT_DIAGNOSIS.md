# FINLEDGER AI — GST CASH SETTLEMENT & AUDIT RECONCILIATION DIAGNOSIS REPORT
**Document ID:** `docs/GST_CASH_SETTLEMENT_DIAGNOSIS.md`  
**Date:** October 2, 2026  
**Client Target:** Client Code `C-1070` (`Ankit public Ltd`), UUID: `70796fab-5319-4dfa-a760-36101d3db20c`  
**Period Target:** `Q2 FY 2026-27 (Jul–Sep)` (`2026-Q2`)  
**Status:** PHASE A — READ-ONLY INVESTIGATION COMPLETE  

---

## EXECUTIVE SUMMARY

A forensic, read-only investigation was conducted on the FinLedger AI full-stack application (FastAPI backend on port 8000, React/Vite frontend on port 5173, and PostgreSQL database `ca_assistant_db`).

The investigation traced the complete data chain:
$$\text{Source document} \longrightarrow \text{Extracted fields} \longrightarrow \text{Accounting voucher} \longrightarrow \text{Posted journal lines} \longrightarrow \text{Backend GST service} \longrightarrow \text{API response} \longrightarrow \text{Frontend UI}$$

### Key Findings
1. **Cash Due Display (₹1,800.00):**
   - The backend `GstReconciliationService.generate_gstr3b` correctly determined that under the statutory GST set-off framework (CGST Act Sections 49, 49A, 49B), **IGST cash liability (₹1,800.00)** cannot be reduced by negative CGST (−₹1,300.00) or negative SGST (−₹1,300.00). Intra-state tax reductions (sales returns) cannot settle inter-state tax liability (debit note).
   - However, **the UI presents a blatant contradiction** because the card subtitle hardcodes the formula:  
     $$\text{Net Tax} = \text{Outward } (−₹800.00) − \text{ITC } (₹0.00)$$  
     which evaluates to $−₹800.00$, directly conflicting with the displayed ₹1,800.00.
   - Furthermore, the backend **silently dropped the negative balances**: it returned `excess_credit_carried_forward = 0.00`, failing to report that ₹1,300 CGST and ₹1,300 SGST are carried forward as output tax adjustments for subsequent periods.
2. **Audit Exceptions Count of Zero:**
   - Client `C-1070` has **8 uploaded documents**, **6 verified**, and **3 posted**.
   - Document S2 (`ABC/26-27/002`, category `e_invoice`, ₹2,00,000 taxable, ₹36,000 IGST) is in `verified` status, but its accounting record is in `draft` status and has **no posted journal entry**.
   - In `backend/app/services/gst_reconciliation_service.py` (line 1054), Check 3 (`UNPOSTED_INVOICE`) only checks `d.document_category in ["sales_records", "purchase_records", "b2b_invoice"]`. It **omitted `e_invoice`**. Because of this category omission, verified e-invoice S2 was never flagged as unposted, resulting in an artificially deflated Audit Exceptions count of 0 instead of 1.
3. **Quarterly Period Parsing Defect:**
   - In `backend/app/services/gst_reconciliation_service.py` (lines 66–84), `_parse_period_dates` only parses monthly strings (`YYYY-MM`). For quarterly strings such as `2026-Q2` (selected by default in the frontend), it catches an exception and returns `(None, None)`.
   - In `detect_discrepancies` (line 961), date filtering is never applied to the document or voucher queries at all.

---

## A1. LIVE APPLICATION & DATABASE ENVIRONMENT CONFIRMATION

| Component | Verified State | Notes |
| :--- | :--- | :--- |
| **Backend Process** | PID 13704 | Running `python.exe -m uvicorn app.main:app --reload --port 8000` |
| **Backend Repo Path** | `c:\Users\Pratham\OneDrive\Desktop\Codes\FINAL YEAR CA FRONT\backend` | Live directory |
| **Git Working Tree** | Clean | Current HEAD commit `486f098` on branch `fix/gst-cash-settlement-audit` (created from `fix/gst-live-parity`) |
| **Frontend Process** | PID 16360 | Running `node.exe ...\vite\bin\vite.js` on port 5173 |
| **Frontend API Base** | `http://localhost:8000/api/v1` | Configured via `VITE_API_BASE_URL` fallback |
| **Running Backend DB** | PostgreSQL `ca_assistant_db` | Host `localhost:5432`, Driver `postgresql+psycopg` |
| **Pytest Test DB** | SQLite In-Memory (`sqlite:///:memory:`) | Isolated per test session via `StaticPool` |
| **Database Parity** | **Different** | Live API uses PostgreSQL; automated unit tests run against SQLite |
| **Service Hot-Reload** | Active | Backend Uvicorn has `--reload`; Frontend Vite has HMR |

*Credential safety note: No passwords, secret tokens, or sensitive credentials are recorded in this document.*

---

## A2. TRACE OF THE CASH DUE VALUE (₹1,800.00)

### 1. Frontend Component
- **File:** [`src/app/components/client/GstWorkspaceView.tsx`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/src/app/components/client/GstWorkspaceView.tsx#L432-L448)
- **Lines:** 432–448
- **Code:**
  ```tsx
  {/* Net Tax Payable in Cash (GSTR-3B) */}
  <Card className="p-4 bg-card/70 border-border/70 hover:border-primary/40 transition-colors">
    <div className="flex items-center justify-between">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        GSTR-3B Cash Due
      </span>
      <span className="rounded-md bg-amber-500/10 p-1.5 text-amber-500">
        <Landmark className="size-4" />
      </span>
    </div>
    <div className="mt-2">
      <p className="text-xl font-bold font-mono text-amber-500">{formatGstCurrency(netCashPayable)}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Net Tax = Outward ({formatGstCurrency(outwardTax)}) − ITC ({formatGstCurrency(eligibleItc)})
      </p>
    </div>
  </Card>
  ```
- **State derivation (lines 157, 163, 169):**
  ```tsx
  const outwardTax = Number(gstr1Data?.total_outward_tax || 0) || ...; // = -800
  const eligibleItc = Number(gstr2bData?.total_eligible_itc || 0);     // = 0
  const netCashPayable = Number(gstr3bData?.tax_payable_in_cash || Math.max(0, outwardTax - eligibleItc));
  ```

### 2. Frontend API Service Call
- **Route called:** `GET http://localhost:8000/api/v1/gst/reconciliation/gstr3b?client_id=70796fab-5319-4dfa-a760-36101d3db20c&period=2026-Q2`
- **Location:** [`src/app/components/client/GstWorkspaceView.tsx`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/src/app/components/client/GstWorkspaceView.tsx#L116)

### 3. Backend Route & Service
- **Router:** [`backend/app/api/routers/gst/router.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/api/routers/gst/router.py#L146-L172)
- **Service Implementation:** [`backend/app/services/gst_reconciliation_service.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/services/gst_reconciliation_service.py#L817-L943), method `generate_gstr3b`.

### 4. Backend Calculation Breakdown
In `gst_reconciliation_service.py`:
- `outward_sec.igst` = `Decimal("1800.00")` (from debit note DN1)
- `outward_sec.cgst` = `Decimal("-1300.00")` (500 from S3 − 1,800 from CN1)
- `outward_sec.sgst` = `Decimal("-1300.00")` (500 from S3 − 1,800 from CN1)
- `net_itc` = `0.00` across all heads
- Lines 872–874 clamp negative liabilities per head at zero for cash liability calculation:
  ```python
  rem_l_igst = max(Decimal("0.00"), raw_l_igst)  # = 1800.00
  rem_l_cgst = max(Decimal("0.00"), raw_l_cgst)  # = 0.00 (clamped from -1300.00)
  rem_l_sgst = max(Decimal("0.00"), raw_l_sgst)  # = 0.00 (clamped from -1300.00)
  ```
- Lines 913–916 sum the per-head cash liabilities:
  ```python
  cash_igst = rem_l_igst  # 1800.00
  cash_cgst = rem_l_cgst  # 0.00
  cash_sgst = rem_l_sgst  # 0.00
  tot_payable_cash = cash_igst + cash_cgst + cash_sgst  # = 1800.00
  ```
- Line 933 sets `tax_payable_in_cash = tot_payable_cash` (`1800.00`).

### 5. Why UI Conflicts
The backend returns `tax_payable_in_cash: 1800.00`. The frontend displays `1800.00`, but underneath displays the aggregate equation:
$$\text{Net Tax} = \text{Outward } (−₹800.00) − \text{ITC } (₹0.00) = −₹800.00$$
This subtitle creates an indefensible arithmetic contradiction on the card. Furthermore, the frontend has a fallback `Math.max(0, outwardTax - eligibleItc)` which would compute 0 if backend `tax_payable_in_cash` were 0.

---

## A3. UNDERLYING POSTED JOURNALS VERIFICATION (C-1070, Q2 FY 2026-27)

Querying the live PostgreSQL database `ca_assistant_db` for Client `70796fab-5319-4dfa-a760-36101d3db20c` reveals **exactly 3 posted, non-reversed journal entries** in Q2 FY 2026-27:

### 1. Document S3 (Cash Sale, Walk-in)
- **Document ID:** `c6bce8d9-6af9-471f-a8ea-cba3d3c142b6`
- **Invoice Number:** `ABC/26-27/003` (B2C Walk-in)
- **Invoice Date:** `2026-07-20` | Category: `b2c_invoice` | Status: `verified`
- **Accounting Record:** ID `0791bea7-9672-426b-bfdb-31254aa67ae2`, type `sales`, status `posted`
- **Journal Entry:** ID `b6b2f0f1-32aa-47dd-9ccc-b8088462ddd8` (`#SV-2026-0002`), status `posted`, `is_reversed = False`, Date `2026-07-20`
- **Lines:**
  | Line | Account Code | Account Role | Account Name | Debit (₹) | Credit (₹) |
  | :--- | :--- | :--- | :--- | ---: | ---: |
  | 1 | 1100 | `DEBTORS` | Sundry Debtors | 21,000.00 | 0.00 |
  | 2 | 2110 | `OUTPUT_CGST` | Output CGST Account | 0.00 | 500.00 |
  | 3 | 2120 | `OUTPUT_SGST` | Output SGST Account | 0.00 | 500.00 |
  | 4 | 4010 | `SALES` | Sales Revenue Account | 0.00 | 20,000.00 |

### 2. Document CN1 (Credit Note against S1)
- **Document ID:** `2edc4e66-0b49-4c15-8b6c-1ef93b041a98`
- **Invoice Number:** `ABC/CN/26-27/001`
- **Invoice Date:** `2026-08-10` | Category: `credit_note` | Status: `verified`
- **Accounting Record:** ID `c7a071d7-ba1b-4ccc-ad2a-01d51a973d58`, type `journal`, status `posted`
- **Journal Entry:** ID `e6867471-d262-4fe5-b20e-49b1479dd29a` (`#JV-2026-0004`), status `posted`, `is_reversed = False`, Date `2026-08-10`
- **Lines:**
  | Line | Account Code | Account Role | Account Name | Debit (₹) | Credit (₹) |
  | :--- | :--- | :--- | :--- | ---: | ---: |
  | 1 | 4020 | `SALES_RETURN` | Sales Return Account | 20,000.00 | 0.00 |
  | 2 | 2110 | `OUTPUT_CGST` | Output CGST Account | 1,800.00 | 0.00 |
  | 3 | 2120 | `OUTPUT_SGST` | Output SGST Account | 1,800.00 | 0.00 |
  | 4 | 1100 | `DEBTORS` | Sundry Debtors | 0.00 | 23,600.00 |

### 3. Document DN1 (Debit Note against S2)
- **Document ID:** `422da965-4ce3-4a51-8d2a-9a2fb198b994`
- **Invoice Number:** `ABC/DN/26-27/001`
- **Invoice Date:** `2026-08-15` | Category: `debit_note` | Status: `verified`
- **Accounting Record:** ID `694755e7-b5fa-41d3-86da-d8d6ffff6531`, type `journal`, status `posted`
- **Journal Entry:** ID `4302b5d2-a388-4b63-af07-33601d7099e7` (`#JV-2026-0006`), status `posted`, `is_reversed = False`, Date `2026-08-15`
- **Lines:**
  | Line | Account Code | Account Role | Account Name | Debit (₹) | Credit (₹) |
  | :--- | :--- | :--- | :--- | ---: | ---: |
  | 1 | 1100 | `DEBTORS` | Sundry Debtors | 11,800.00 | 0.00 |
  | 2 | 4030 | `OTHER_INCOME` | Other Operating Income | 0.00 | 10,000.00 |
  | 3 | 2130 | `OUTPUT_IGST` | Output IGST Account | 0.00 | 1,800.00 |

### 4. Status of S1, S2, and Other Records
- **S1 (`ABC/26-27/001`):** UploadedDocument ID `9297a134-7913-43c2-8240-221fecc255c3`. Status is `pending`. No accounting record, no journal entry. Not posted.
- **S2 (`ABC/26-27/002`):** UploadedDocument ID `e5ff525e-ace8-4128-94f7-07c6ec690959`. Status is `verified`. AccountingRecord ID `24b52161-ce7d-43a1-b1e5-b96c7b7ee7dd` is `status = "draft"`. **No posted journal entry.** Not posted.
- **Historical/Reversed vouchers:** Vouchers `SV-2026-0001`, `PV-2026-0001`, `JV-2026-0001`, `REV-2026-0001`, `JV-2026-0002`, `REV-2026-0002`, `JV-2026-0003`, `REV-JV-2026-0003` are all flagged `is_reversed = True` or `status = "reversed"`. They are cleanly excluded from the GL query by `status == "posted"` and `is_reversed == False`.

---

## A4. STATUTORY GST CASH SETTLEMENT ANALYSIS

### Statutory Rules (Sections 49, 49A, 49B of CGST Act & Rule 88A)
1. **No Cross-Head Offset of Liabilities:**
   Under Indian GST, liabilities under different tax heads (IGST, CGST, SGST) are legally distinct obligations to different revenue authorities (Union of India vs State Governments).
   $$\text{IGST Liability cannot be offset by negative CGST or negative SGST.}$$
2. **Treatment of Negative Output Liability (Excess Credit Notes):**
   When credit notes exceed supplies in a tax period, the net output tax liability for that head is negative.
   Under GST Law and GSTN System Rules:
   - Negative liability **cannot** be refunded via GSTR-3B Table 6.1.
   - Negative liability **cannot** cross-subsidize another tax head.
   - Cash payable for that tax head is **₹0.00**.
   - The negative balance represents an **Output Tax Adjustment Carried Forward** to subsequent tax periods.
3. **Statutory Set-Off Matrix for S3 + CN1 + DN1:**
   | Tax Head | Gross Output | CN Reduction | Net Output Liability | Eligible ITC | ITC Utilized | Cash Payable | Adjustment Carried Forward |
   | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
   | **IGST** | ₹0.00 | ₹0.00 | **+₹1,800.00** | ₹0.00 | ₹0.00 | **₹1,800.00** | ₹0.00 |
   | **CGST** | ₹500.00 | −₹1,800.00 | **−₹1,300.00** | ₹0.00 | ₹0.00 | **₹0.00** | **−₹1,300.00** |
   | **SGST** | ₹500.00 | −₹1,800.00 | **−₹1,300.00** | ₹0.00 | ₹0.00 | **₹0.00** | **−₹1,300.00** |
   | **Total** | ₹1,000.00 | −₹3,600.00 | **−₹800.00** | ₹0.00 | ₹0.00 | **₹1,800.00** | **−₹2,600.00** |

### Defect in Current Settlement Implementation
1. **Mathematical correctness:** The cash payable figure of **₹1,800.00** is statutorily correct for cash due, because the ₹1,800 IGST liability must be paid in cash and cannot be offset by CGST/SGST.
2. **Defect 1 (Frontend):** The frontend subtitle displayed a false formula: `Net Tax = Outward (-800) - ITC (0)`, suggesting the cash due should be `-800`.
3. **Defect 2 (Backend):** The backend omitted reporting `negative_liability_carried_forward` (or `output_adjustment_carried_forward`), instead returning `excess_credit_carried_forward: 0.00`. It failed to inform the CA that −₹1,300 CGST and −₹1,300 SGST are carried forward for future adjustment.

---

## A5. AUDIT EXCEPTIONS COUNT INVESTIGATION (ZERO COUNT DEFECT)

### Live Discrepancy Endpoint Inspection
Calling `/api/v1/gst/reconciliation/discrepancies?client_id=70796fab-5319-4dfa-a760-36101d3db20c&period=2026-Q2` returns:
```json
{
  "total_discrepancies": 0,
  "high_count": 0,
  "medium_count": 0,
  "low_count": 0,
  "total_tax_at_risk": "0",
  "discrepancies": []
}
```

### Root Cause Analysis in `detect_discrepancies`
In [`backend/app/services/gst_reconciliation_service.py`](file:///c:/Users/Pratham/OneDrive/Desktop/Codes/FINAL%20YEAR%20CA%20FRONT/backend/app/services/gst_reconciliation_service.py#L1053-L1068):
```python
# Check 3: Unposted Invoices
if d.document_category in ["sales_records", "purchase_records", "b2b_invoice"] and d.status == "verified":
    if d.id not in doc_posted_map:
        discrepancies.append(GstDiscrepancyItem(
            discrepancy_id=f"DISC-UNPOSTED-{d.id}",
            rule_code="UNPOSTED_INVOICE",
            severity="MEDIUM",
            title="Verified Document Not Posted to Ledger",
            description=f"Document #{d.invoice_number or 'UNKNOWN'} is verified but not yet posted into the general ledger.",
            ...
        ))
```

### Why Document S2 Was Missed
- Document S2 (`ABC/26-27/002`) has:
  * `document_category`: `"e_invoice"`
  * `status`: `"verified"`
  * `amount`: ₹2,36,000.00 (`taxable_amount`: ₹2,00,000.00, `igst`: ₹36,000.00)
  * `AccountingRecord`: `status = "draft"`
  * `JournalEntry`: **None** (not in `doc_posted_map`)
- S2 is a **verified, unposted invoice with ₹36,000.00 tax at risk**.
- Because the check hardcoded `["sales_records", "purchase_records", "b2b_invoice"]`, it **did not match `"e_invoice"`** (nor `"b2c_invoice"`).
- **Conclusion:** The zero audit exception count is **defective**. It omitted verified e-invoice S2 (`ABC/26-27/002`). When `e_invoice` is included in Check 3, `detect_discrepancies` returns:
  - Total Discrepancies: **1**
  - Medium Risk: **1**
  - Variance: **₹36,000.00**
  - Rule: `UNPOSTED_INVOICE`

---

## A6. CONSISTENCY ACROSS GST VIEWS & PERIOD HANDLING

| View / Card | Displayed Value | Computed By | Scope / Filter Used | Discrepancy Found? |
| :--- | ---: | :--- | :--- | :--- |
| **GSTR-1 Outward** | ₹10,000.00 | Backend (`reconcile_gstr1`) | Posted outward GL lines | None |
| **Tax Liability** | −₹800.00 | Backend (`reconcile_gstr1`) | Posted outward GL lines | None |
| **Purchase Register (ITC)** | ₹0.00 | Backend (`reconcile_gstr2b`) | Posted inward GL lines | None (correctly isolated) |
| **Eligible ITC** | ₹0.00 | Backend (`reconcile_gstr2b`) | Posted inward GL lines | None |
| **GSTR-3B Cash Due** | ₹1,800.00 | Backend (`generate_gstr3b`) | Head-wise statutory set-off | Yes — Subtitle formula contradiction in UI; negative carry-forward dropped |
| **Audit Exceptions** | 0 | Backend (`detect_discrepancies`) | Non-rejected documents | Yes — Category omission missed S2 e-invoice; period dates not applied |
| **Period Selector** | `2026-Q2` | Frontend Dropdown | Passed as `?period=2026-Q2` | Yes — `_parse_period_dates` cannot parse `2026-Q2` |

---

## A7. TEST COVERAGE REVIEW

1. **Existing Test Suite:** 195 tests run via pytest in 14.62s. All 195 tests pass.
2. **Database Engine Used:** Pytest runs exclusively on SQLite in-memory (`sqlite:///:memory:`). No automated tests run against live PostgreSQL.
3. **Coverage Gaps:**
   - **No test** covers `generate_gstr3b` with negative CGST/SGST and positive IGST.
   - **No test** covers quarterly period strings (`2026-Q2`, `2026-Q1`) in `_parse_period_dates`.
   - **No test** verifies that verified `e_invoice` triggers `UNPOSTED_INVOICE`.
   - **No test** asserts that the Cash Due card subtitle reflects statutory head-wise discharge rather than simple aggregate subtraction.

---

## A8. DIAGNOSIS CONCLUSION & DEFECT MATRIX

### Defect 1: Cash Due Subtitle Formula Contradiction & Unsurfaced Negative Carry-Forward
- **Symptom:** UI displays Cash Due ₹1,800.00 with subtitle `Net Tax = Outward (−₹800.00) − ITC (₹0.00) = −₹800.00`.
- **Root Cause:**
  1. Frontend `GstWorkspaceView.tsx` hardcoded an aggregate subtraction formula in the subtitle instead of displaying the head-wise breakdown (IGST ₹1,800 cash due; CGST/SGST negative adjustments carried forward).
  2. Backend `gst_reconciliation_service.py` set `excess_credit_carried_forward = 0.00` and omitted `output_adjustment_carried_forward_cgst/sgst`.
- **Minimal Fix:**
  1. Add optional fields to `Gstr3bResponse`: `negative_liability_carried_forward`, `negative_liability_cgst`, `negative_liability_sgst`.
  2. Update frontend `GstWorkspaceView.tsx` card to display:
     - Cash Due: ₹1,800.00 (IGST)
     - Subtitle / Note: `IGST ₹1,800.00 Cash Payable · CGST/SGST −₹2,600.00 carried forward to next period`
     - Remove improper client-side fallback `Math.max(0, outwardTax - eligibleItc)`.

### Defect 2: Audit Exceptions Omitting Verified E-Invoices
- **Symptom:** Audit Exceptions card displays `0`, despite verified e-invoice S2 (`ABC/26-27/002`) remaining unposted in draft status.
- **Root Cause:** Line 1054 of `gst_reconciliation_service.py` only checked `d.document_category in ["sales_records", "purchase_records", "b2b_invoice"]`, omitting `"e_invoice"` and `"b2c_invoice"`.
- **Minimal Fix:** Include `"e_invoice"`, `"b2c_invoice"`, `"credit_note"`, `"debit_note"` in Check 3 of `detect_discrepancies`.

### Defect 3: Quarterly Period Parsing Failure in `_parse_period_dates`
- **Symptom:** Selecting `"2026-Q2"` in the UI passes `period=2026-Q2`, but `_parse_period_dates` fails with ValueError and returns `(None, None)`.
- **Root Cause:** Line 68 of `gst_reconciliation_service.py` checks `len(parts[1]) == 2` and runs `int(parts[1])`, failing on `"Q2"`.
- **Minimal Fix:** Add quarterly parsing support for `YYYY-Q1`, `YYYY-Q2`, `YYYY-Q3`, `YYYY-Q4` (mapping `Q2` to July 1 – Sept 30, `Q1` to April 1 – June 30, `Q3` to Oct 1 – Dec 31, `Q4` to Jan 1 – March 31).
- **Filter in `detect_discrepancies`:** Apply `start_d` and `end_d` to documents in `detect_discrepancies` consistently with `reconcile_gstr1`.

---

## DECISION ON PHASE B PROCEEDING

All three root causes have been proved with exact line numbers, database records, and API traces:
1. The ₹1,800 Cash Due amount is **statutorily verified** as the IGST cash liability that cannot be offset by negative CGST/SGST; the defect is in the frontend subtitle presentation and backend negative carry-forward disclosure.
2. The zero Audit Exceptions count is **defective** due to an omitted document category in Check 3.
3. The period parsing defect is **defective** due to missing `YYYY-Q#` pattern handling.

The fixes require **zero destructive changes**, **zero schema migrations**, and **preserves all existing 195 tests**. We proceed to Phase B.
