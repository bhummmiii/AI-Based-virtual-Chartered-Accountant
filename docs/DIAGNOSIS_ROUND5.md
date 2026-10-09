# Round 5 Diagnosis & Audit Report: Filing by Frequency & Statutory Controls

**Date:** 09-Oct-2026  
**Client:** C-1071 (`oggy pvt ltd`, GSTIN `27AABCA1234A1Z5`, Maharashtra)  
**Target Branch:** `fix/filing-by-frequency` (based on `fix/gst-parity-round4` @ `1e6e45c`)  
**Clock Today:** 2026-10-09  

---

## 1. Executive Summary & Verification of Invariants

All baseline numbers from Round 4 on the live UI remain intact and strictly verified:
- **Table 3.1:** Taxable ₹300,000.00 | IGST ₹36,000.00 | CGST ₹7,700.00 | SGST ₹7,700.00 | Total Tax ₹51,400.00.
- **GSTR-1:** B2B 2 invoices ₹300,000.00 (tax ₹54,000.00); B2C Small S3 ₹20,000.00 (tax ₹1,000.00); CN1 CDNR with `27AAAPM5678B1Z2` (-₹20,000.00; CGST -₹1,800.00; SGST -₹1,800.00); Debit notes 0.
- **Purchase Register:** P1 Pune Compu Traders `27AABCP9876D1Z4` (₹100,000.00; CGST ₹9,000.00; SGST ₹9,000.00); PDN1 TN Raw Materials Ltd `33AABCT1111E1Z6` (-₹10,000.00; IGST -₹1,800.00); Inward taxable ₹90,000.00; Net ITC ₹16,200.00.
- **Table 4 ITC Statement:** (A) IGST 0 / CGST 9,000 / SGST 9,000 = 18,000; (B) IGST 1,800; (C) IGST -1,800 / CGST 9,000 / SGST 9,000 = 16,200 ("ITC available 18,000, reversed 1,800, net 16,200").
- **Table 6 Cash Settlement:** Cash IGST ₹35,200.00 / CGST ₹0.00 / SGST ₹0.00; "ITC reversal payable IGST 1,800"; Closing ITC carried forward 0/0/0.
- **Table 12 HSN:** 4820 Notebooks @ 5% ₹20,000 (tax ₹1,000); 9401 Chairs @ 18% ₹80,000 (tax ₹14,400); 998314 Software @ 18% ₹200,000 (tax ₹36,000). Total: ₹300,000 / ₹51,400.
- **Pre-Migration DB Backup:** Completed and verified: `docs/backups/ca_assistant_db_round5_pre.sql` (380,976 bytes).

---

## 2. Phase A Audit Questions (A1–A7)

### A1. Client C-1071 Stored `return_frequency` & Audit Trail
- **Live DB Query Output:**
  ```text
  ID: 915b40bc-cfff-49e1-87ac-f79fa861c0e6
  client_code: C-1071
  company_name: oggy pvt ltd
  client_type: company
  return_frequency: Monthly
  created_at: 2026-10-05 14:24:05.146816+05:30
  updated_at: 2026-10-06 12:38:03.605068+05:30
  ```
- **Analysis:**
  - `client_type` is `"company"` (neither `"monthly"` nor `"quarterly"`).
  - On 2026-10-06 12:38:03, `client_service.py:161` or an update payload defaulted `return_frequency` to `"Monthly"` because `data.clientType` was missing or `"company"`, falling back to `"Monthly"`.
  - In `backend/app/services/client_service.py`:
    - Line 161: `return_frequency=(data.clientType or "Monthly").capitalize()`
    - Line 339: `r_freq = (client.return_frequency or ("Monthly" if b_cycle == "Monthly" else "Quarterly")).capitalize()`
    - Line 407: `patch["return_frequency"] = data.clientType.capitalize()`
    - Line 745: `r_freq = (client.return_frequency or ("Monthly" if c_type == "Monthly" else "Quarterly")).capitalize()`
  - Unit tests created separate scratch clients in SQLite / isolated sessions; they did not alter C-1071 in PostgreSQL.
  - As instructed, the owner confirms C-1071 must be **Quarterly**. A dedicated script `scripts/set_return_frequency.py` with `--dry-run` default and `--to Quarterly` will be provided and run.

---

### A2. Source of Page Badge, Dialog Text, and Due Dates
- **Frontend Badge & Dialog Text:**
  - `src/app/pages/ClientWorkspace.tsx:749`:
    `<GstWorkspaceView ... returnFrequency={client?.clientType ?? "Monthly"} />`
    Passes `client.clientType` (which is `"company"`) or falls back to `"Monthly"`.
  - `src/app/context/AppContext.tsx:46-62`:
    ```typescript
    const rawType = (raw.client_type || "").toLowerCase();
    const clientType = rawType.includes("month")
      ? "Monthly"
      : rawType.includes("quarter")
      ? "Quarterly"
      : (raw.return_frequency || "Monthly");
    ```
    Silently defaulted to `"Monthly"` when `client_type` was `"company"` and `return_frequency` was null/missing.
  - `src/app/components/client/GstWorkspaceView.tsx:1998, 2041`:
    Displays `{returnFrequency} filing profile` and `Computed by GST rules for {returnFrequency} {filingForm}`.
- **Backend Defaults:**
  - `backend/app/api/routers/gst/router.py:280`:
    `client_freq = (client.return_frequency or "Monthly").strip()` (silent default to Monthly).
- **Remedy:** Implement `get_filing_profile(client)` as the single source of truth in the backend. Never silently default to Monthly. If frequency is None/unrecognized, return `None` and display the setup notice.

---

### A3. Current Filing Endpoint (`POST /records`) Validation & Storage
- **File:** `backend/app/api/routers/gst/router.py:270-458`
- **Validation:**
  - Rejects empty or `"all"` period.
  - Checks `"Q" in period` vs `client_freq` (which was silently defaulting to `"Monthly"`).
  - Checks `end_d >= today` (rejects unended periods).
  - Checks duplicate filings: queries `GSTRecord` where `client_id`, `period`, `return_type` match and record is not voided.
  - Checks negative outward liabilities (rejects if any head < 0).
  - Checks active blocking discrepancies (`high_count > 0`).
- **Storage:**
  - Computes and stores authoritative `taxable_turnover`, `tax_liability`, `itc_claimed`, `status="filed"`, `payment_status="paid"`.
  - Ignores client-supplied taxable/tax amounts.
  - Missing: `period_type` column (e.g. "quarterly" / "monthly") and `frequency_at_filing` column on `GSTRecord`.

---

### A4. Source of "Filed Returns (n)" Tab Count Discrepancy
- **Filed Counter (Step 4 Card):**
  - `src/app/components/client/GstWorkspaceView.tsx:273`:
    `const filedCount = filingRecords.filter(r => (r.filing_status || r.status) === 'filed' && r.filing_status !== 'voided' && !r.void_reason).length;`
    Filters out voided records, correctly returning **0**.
- **Tab Trigger Label:**
  - `src/app/components/client/GstWorkspaceView.tsx:694`:
    `<TabsTrigger value="history" ...> <Landmark className="size-4" /> Filed Returns ({filingRecords.length}) </TabsTrigger>`
    Uses `filingRecords.length`, which includes the voided 2026-10 record, displaying **1**.
- **Remedy:** Update tab trigger count to `filingRecords.filter(r => (r.filing_status || r.status) === 'filed' && r.filing_status !== 'voided' && !r.void_reason).length`.

---

### A5. Alert Rule for `DUPLICATE_INVOICE`
- **File:** `backend/app/services/gst_reconciliation_service.py:1517-1529`
- **Current Behavior:**
  - When duplicate document `3c3ecc9e` is detected, it always generates:
    `rule_code="DUPLICATE_INVOICE", severity="HIGH"`.
  - Even though `3c3ecc9e.status == "rejected"` and `rejection_reason == "DUPLICATE"`, it still raises a HIGH alert.
  - This HIGH alert inflates `high_count` to 1, blocking filing under `router.py:421`.
- **Remedy:** When duplicate document status is `"rejected"`, downgrade alert to `rule_code="DUPLICATE_REJECTED", severity="INFO"`, message: *"Rejected duplicate ABC/26-27/001 is excluded from all figures - you may delete it"*.

---

### A6. Status of Y5 Items (Verification)
1. **E-Invoice E1:**
   - Doc ID: `3785d117-2d2a-4131-b584-d169cb09f034`
   - Invoice Number: `ABC/26-27/002`
   - IRN: `3025278422a1084f9e226a33d0527b65662e4c0a3c1d0b8a087f7d506021f2a4`
   - Linked to: Sales invoice S2 (`aa1c50bb-571f-45a8-bbb0-55416a7463ad`)
   - Status: **CORRECT**.
2. **E-Way Bill EWB1:**
   - Doc ID: `7c72187a-8718-415e-b8a9-cff2f0e1ab19`
   - E-Way Bill Number: `381012345678`
   - Linked to: Sales invoice S1 (`b43c25ec-f9e3-4fec-9cc9-e8698f411143`)
   - Status: **CORRECT**.
3. **PDN1 Voucher Header Party:**
   - Replacement voucher: `JV-2026-0002-CORR`
   - Counterparty: `TN Raw Materials Ltd` (`33AABCT1111E1Z6`)
   - Reversal voucher: `REV-JV-2026-0002`
   - Status: **CORRECT** in double-entry ledger.
4. **Payment Voucher Modal Labels:**
   - In `src/app/components/client/VoucherDetailModal.tsx`:
     - Bank as "Cash & Bank": Line 498 (`{isPaymentVoucher ? "Cash & Bank" : "Party Account"}`). **CORRECT**.
     - "Amount paid": Line 508 (`{isPaymentVoucher ? "Amount paid" : "Total Value"}`). **CORRECT**.
     - "Tax paid - CGST/SGST/IGST": Payment voucher settlement card will explicitly display the per-head tax paid breakdown.

---

### A7. Source of Dashboard Notifications & Tasks
- **Tasks (`Today's Tasks`):** Dynamically generated in `Dashboard.tsx:149-210` (`derivedTasks`) based on real clients and their GST/Audit status. Interactive toggle persists in `localStorage`.
- **Activity (`Recent Activity`):** Data-driven from `GET /api/v1/invoices/recent` with fallback to workspace activity.
- **Deadlines (`Upcoming Deadlines`):** Static dates mapped to active clients.
- **Statutory Circulars:** Static educational circular ("Circular 214/8/2026") in mock service.
- **Action (G9):** Add a subtle `"Sample data"` badge to static/sample widgets on the Dashboard without modifying live business logic.

---

## 3. Implementation Plan (G0–G9)
1. **G0 (Y5):** Verification & minor label alignment for payment voucher modal.
2. **G1 (Y1):** Single source of truth `get_filing_profile(client)` + frequency scripts. Run dry-run, then apply `--to Quarterly` for C-1071.
3. **G2:** Additive read endpoints: `GET /api/v1/gst/filing-options` and `GET /api/v1/gst/filing-preview`.
4. **G3 (Y2):** Rebuild filing dialog with internal period dropdown, blockers handling, and frequency badges.
5. **G4:** Due date configuration table (Category X on 22nd, Category Y on 24th, monthly on 20th).
6. **G5:** Server enforcement on save, additive `period_type` & `frequency_at_filing`, period locking.
7. **G6 (Y4):** Rejected duplicate invoice alert is INFO `DUPLICATE_REJECTED` (non-blocking).
8. **G7 (Y3):** "Filed Returns (n)" tab count excludes voided records.
9. **G8:** Data helpers (`scripts/reverse_voucher.py`, deletion guards check).
10. **G9 (Y6):** Sample data label on dashboard.
