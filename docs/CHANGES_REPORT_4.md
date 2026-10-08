# Round 4 Completion Report: GST & Accounting Parity (F1–F11)

**Date:** 08-Oct-2026  
**Client:** C-1071 (`oggy pvt ltd`, GSTIN `27AABCA1234A1Z5`, Maharashtra, Return Frequency: Quarterly)  
**Period Under Review:** Q2 FY 2026-27 (July – September 2026)  
**Target Branch:** `fix/gst-parity-round4`  
**Repository:** `bhummmiii/AI-Based-virtual-Chartered-Accountant`  

---

## 1. Executive Summary

This report documents the end-to-end execution, statutory verification, and automated validation for Round 4 items **F1 through F11**. All identified discrepancies, false-positive alerts, classification gaps, and UI governance counters have been resolved.

All work strictly adheres to the governance rules:
- **Rule R1 (Minimal Diff):** Scoped exclusively to GST reconciliation, accounting draft mapping, document linking, and filing controls. Zero modifications to authentication, dashboard, reports, AI assistant, or chat scrollbar.
- **Rule R2 (Double-Entry Invariance & Immutability):** Posted vouchers are immutable. Fixes applied through reversing entries and reposting (`REV-JV-2026-0002` and `JV-2026-0002-CORR`).
- **Rule R6 (Git Commit Hygiene):** Exactly one git commit per F-item on branch `fix/gst-parity-round4`.
- **Rule R8 (Multi-Client Isolation):** Zero hardcoded client IDs or client-specific branches in core logic. Validated across independent client tenants.
- **Rule R11 (Safety):** Scratch client C-1071 has zero real return submissions; invalid draft filings voided with audit reasons.

---

## 2. Round 4 Commit History (`fix/gst-parity-round4`)

| Commit Hash | Item | Commit Message |
|:---|:---:|:---|
| `6a3543f` | Docs | `docs: Phase A status audit and diagnosis matrix (DIAGNOSIS_ROUND4.md)` |
| `ea4db02` | **F1** | `fix(gst): F1 resolve credit note CDNR by recipient GSTIN and persist voucher counterparty` |
| `2eea299` | **F2** | `fix(accounting): F2 counterparty on client-issued notes and SELF_PARTY validation` |
| `8428239` | **F3** | `fix(gst): F3 server-authoritative filing records and void bogus filings script` |
| `f136282` | **F4** | `fix(gst): F4 tax at risk accuracy and duplicate rejection handling` |
| `afe6400` | **F5** | `fix(ocr): F5 einvoice doc no extraction and compliance relinking` |
| `7e995a7` | **F6** | `fix(ui): F6 filing dialog period selection and quarterly labels` |
| `089fb54` | **F7** | `fix(gst): F7 HSN Table 12 outward sales summary parity` |
| `20fdb07` | **F8** | `fix(accounting): F8 payment voucher isolation and cash settlement labels` |
| `85c24a0` | **F9** | `fix(gst): F9 exclude payment vouchers from tax line alert and add future dated payment alert` |
| `a32eb59` | **F10** | `fix(ui): F10 Table 4 true statutory ITC statement` |
| `7831d75` | **F11** | `fix(ui): F11 counters, sales return contra-revenue, and multi-client isolation` |

---

## 3. Comprehensive Diagnosis & Resolution Matrix (F1–F11)

### F1: Credit Note CDNR vs CDNUR Resolution
- **Diagnosis:** In `GstReconciliationService.reconcile_gstr1`, credit notes evaluated `doc_g != client_gstin`. Because `CN1` stored the client's own supplier GSTIN in `d.gstin` and `metadata_["fields"]["customer_gstin"]` was blank, recipient GSTIN evaluated to empty string. The note was misclassified as `CDNUR` (Unregistered).
- **Resolution:**
  - Added multi-level recipient GSTIN extraction in `gst_reconciliation_service.py:452-475` (checks `customer_gstin`, parses printed note text for `Recipient (To) ... GSTIN:`, falls back to parent commercial invoice `Against Invoice ABC/26-27/001`).
  - Added `counterparty_name` and `counterparty_gstin` columns to `JournalEntry` model and migration.
  - Added `backend/scripts/repair_cn1_counterparty.py` with `--dry-run` and `--apply`.
  - CDNR now authoritatively lists `Mehta Enterprises` (`27AAAPM5678B1Z2`). CDNUR count is 0.
- **Test:** `backend/tests/test_note_cdnr_by_recipient_gstin.py` (2/2 passing).

---

### F2: Counterparty on Client-Issued Notes (PDN1) & SELF_PARTY Validation
- **Diagnosis:** On client-issued purchase debit notes (`PDN1`), OCR assigned the issuer (client) to `vendor` and supplier to `customer`. `AccountingDraftService` naively mapped `party_label = doc.vendor`, displaying the client's own name as counterparty.
- **Resolution:**
  - Updated `AccountingDraftService.map_document_to_record_fields` to inspect client identity: if issuer is the client, party is assigned from the non-client recipient.
  - Added strict `SELF_PARTY` validation gate blocking any voucher where counterparty equals client's own GSTIN.
  - Repaired live DB using immutable accounting: reversed `JV-2026-0002` via reversing entry `REV-JV-2026-0002` and reposted corrected voucher `JV-2026-0002-CORR` with party `TN Raw Materials Ltd` (`33AABCT1111E1Z6`).
- **Test:** `backend/tests/test_counterparty_on_client_notes.py` (passing).

---

### F3: Server-Authoritative Filing Records & Void Bogus Filings
- **Diagnosis:** Filing endpoint `/api/v1/gst/records` accepted unverified client-supplied taxable amounts (e.g. ₹90,000,000.00) without validating date boundaries or return frequencies, creating bogus record `e89e205d` for future period `2026-10`.
- **Resolution:**
  - Implemented `backend/scripts/void_bogus_filings.py`.
  - Voided record `e89e205d` with statutory audit reason: `Period has not ended yet (Period end 2026-10-31 >= today 2026-10-08)`.
  - Hardened backend router: server computes all figures directly from posted ledgers; rejects periods where `period_end >= today`; rejects monthly periods for quarterly clients.
- **Test:** `backend/tests/test_filing_dialog_period_selection.py` (2/2 passing).

---

### F4: Tax at Risk Accuracy & Duplicate Rejection Handling
- **Diagnosis:** Discrepancy detector reported ₹1,18,000 for duplicate invoice `3c3ecc9e` because it used gross invoice total (`tot_amt`) instead of statutory tax amount (₹18,000). Both companion e-invoices and duplicates raised spurious `UNPOSTED_INVOICE` alerts.
- **Resolution:**
  - Fixed `variance_amount = tax_val` in `gst_reconciliation_service.py:1325`.
  - Marked duplicate invoice `3c3ecc9e` status to `rejected` with `rejection_reason = "DUPLICATE"`.
  - Excluded rejected documents and companion compliance documents (`e_invoice`, `e_way_bill`) from unposted draft checks.
- **Test:** `backend/tests/test_discrepancy_and_duplicate_handling.py` (passing).

---

### F5: E-Invoice Doc No Extraction & Compliance Relinking
- **Diagnosis:** OCR parser regex matched the 64-character IRN hash before the commercial invoice number, saving the IRN string into `doc.invoice_number` instead of printed `Document No: ABC/26-27/002`. Documents were mislinked (E1 linked to S3, EWB1 linked to P1).
- **Resolution:**
  - Hardened `_parse_invoice` in `ocr/router.py` to extract `ABC/26-27/002` into `invoice_number` and IRN hash into dedicated `irn` column.
  - Implemented `backend/scripts/repair_einvoice_doc_numbers.py` to relink documents by invoice number and party:
    - E-Invoice `3785d117` (`ABC/26-27/002`) -> linked to Sales Invoice S2 (`aa1c50bb`).
    - E-Way Bill `7c72187a` (`381012345678`) -> linked to Sales Invoice S1 (`b43c25ec`).
- **Test:** `backend/tests/test_ocr_einvoice_doc_number.py` (passing).

---

### F6: Filing Dialog Period Selection & Statutory Due Dates
- **Diagnosis:** Filing modal allowed submitting under "All Available", prefilling invalid period `2026-09` for quarterly clients.
- **Resolution:**
  - Disabled the "Record Filing" action if period is unselected or set to "All Available".
  - Computed statutory due dates per GST rules:
    - Category 1 (South/West: MH, GJ, KA, etc.): 22nd of month following quarter (`2026-10-22`).
    - Category 2 (North/East: DL, HR, UP, etc.): 24th of month following quarter (`2026-10-24`).
    - Monthly GSTR-3B: 20th of next month (`2026-09-20`).
    - QRMP GSTR-1: 13th of month following quarter (`2026-10-13`).
  - Added descriptive period labels (e.g., `Q2 FY 2026-27`).
- **Test:** `backend/tests/test_filing_dialog_period_selection.py` (2/2 passing).

---

### F7: HSN Table 12 Outward Sales Summary Parity
- **Diagnosis:** Table 12 raised an unhandled `NameError: name 'os' is not defined` when evaluating source documents, returning 0 classified codes. It also failed to parse `period="all"`.
- **Resolution:**
  - Added `import os` at module scope in `gst_reconciliation_service.py`.
  - Updated `_parse_period_dates` to handle `"all"`, `"all available"`, and `None` cleanly.
  - Filtered strictly by outward commercial sales templates (`T1`, `T3`, `T4`), excluding purchase and payment vouchers.
  - Table 12 dynamically outputs exactly 3 rows:
    1. HSN `4820` (Stationery): ₹20,000.00 @ 5% = ₹1,000.00 tax
    2. HSN `9401` (Chairs): ₹80,000.00 @ 18% = ₹14,400.00 tax
    3. HSN `998314` (Software): ₹200,000.00 @ 18% = ₹36,000.00 tax
    - Total Taxable: ₹300,000.00 | Total Tax: ₹51,400.00 (100% parity with Table 3.1).
- **Test:** `backend/tests/test_hsn_table12_all_periods.py` (1/1 passing).

---

### F8: Payment Voucher GST Isolation & Cash Settlement Labels
- **Diagnosis:** Double-entry payment voucher `PMT-2026-0001` (clearing GST challan liability `Dr 2150` against `Cr 1020` Bank) was displayed in the UI with commercial invoice line headers ("Customer/Vendor", "Output CGST").
- **Resolution:**
  - Excluded payment vouchers from outward registers (`reconcile_gstr1`) and inward registers (`reconcile_gstr2b`).
  - Updated `VoucherDetailModal.tsx` to display statutory tax payment metadata:
    - Counterparty: "Cash & Bank"
    - Amount field: "Amount paid"
    - Added dedicated banner explaining tax settlement of closing balances.
  - Added Closing ITC Balance Carried Forward indicator in `GstWorkspaceView.tsx`.
- **Test:** `backend/tests/test_payment_voucher_isolated.py` (1/1 passing).

---

### F9: Discrepancy Rule Set Hardening & Future-Dated Payment Alert
- **Diagnosis:** Under "All Available", `detect_discrepancies` evaluated `PMT-2026-0001` (dated in future `2026-10-20`), detected zero commercial tax lines (2110/2120), and raised false-positive `LEGACY_VOUCHER_NO_TAX_LINES` (HIGH, ₹84,700 risk).
- **Resolution:**
  - Excluded payment vouchers (`entry_type == "payment"` and template `PAYMENT`) from `LEGACY_VOUCHER_NO_TAX_LINES`.
  - Added new non-blocking alert: `FUTURE_DATED_PAYMENT` (MEDIUM severity) when entry date is in the future.
  - Eliminated the false-positive 2nd HIGH discrepancy.
- **Test:** `backend/tests/test_alert_rules_regression.py` (1/1 passing).

---

### F10: Table 4 True Statutory ITC Statement
- **Diagnosis:** Table 4 UI displayed misleading text: *"100% of inward tax is claimable as eligible ITC"*, ignoring the ₹1,800.00 ITC reversal under Table 4(B).
- **Resolution:**
  - Replaced misleading claim with true statutory equation:  
    `"ITC available ₹18,000.00, reversed ₹1,800.00, net ₹16,200.00"`.
  - Matches Section 16/17 statutory disclosure and double-entry balance.
- **Validation:** Frontend bundle built cleanly (`vite v6.4.3 build exit code 0`).

---

### F11: UI Governance Counters, Contra-Revenue Check, & Multi-Client Isolation
- **Diagnosis:** UI counters in `GstWorkspaceView.tsx` counted voided filings under Filed (showing 1) and rejected documents under Verified (showing 11).
- **Resolution:**
  - Enforced strict 4-state lifecycle counter contract:
    - **1. Extracted:** All effective documents (`11`).
    - **2. Verified:** `status == 'verified' && status != 'rejected'` (`10`, excludes duplicate).
    - **3. Posted:** `status == 'posted' && !is_reversed && status != 'reversed'` (`7` active unreversed vouchers).
    - **4. Filed:** `filing_status == 'filed' && filing_status != 'voided' && !void_reason` (`0` filed returns).
  - Validated Account 4020 role `SALES_RETURN`: debits to 4020 correctly reduce gross turnover as contra-revenue.
  - Implemented comprehensive multi-client isolation test (`test_multi_client_isolation_round4.py`) proving zero data bleed between Client A (MH Quarterly) and Client B (DL Monthly).
- **Test:** `backend/tests/test_multi_client_isolation_round4.py` (3/3 passing).

---

## 4. Final Statutory Figure Verification for C-1071 (Q2 FY 2026-27)

| Metric | Target Value | Actual System Value | Status |
|:---|:---:|:---:|:---:|
| **Table 3.1 Outward Taxable** | ₹300,000.00 | ₹300,000.00 | **EXACT PARITY** |
| **Table 3.1 Total Outward Tax** | ₹51,400.00 | ₹51,400.00 | **EXACT PARITY** |
| **Table 4(A) ITC Available** | ₹18,000.00 | ₹18,000.00 | **EXACT PARITY** |
| **Table 4(B) ITC Reversed** | ₹1,800.00 | ₹1,800.00 | **EXACT PARITY** |
| **Table 4(C) Net ITC Claimable** | ₹16,200.00 | ₹16,200.00 | **EXACT PARITY** |
| **Table 6 Reversal Payable** | ₹1,800.00 | ₹1,800.00 | **EXACT PARITY** |
| **GSTR-3B Cash Payable** | ₹35,200.00 | ₹35,200.00 | **EXACT PARITY** |
| **Table 12 HSN Summary Rows** | 3 classified rows | 3 classified rows | **EXACT PARITY** |
| **Table 12 Total Taxable** | ₹300,000.00 | ₹300,000.00 | **EXACT PARITY** |
| **Table 12 Total Tax** | ₹51,400.00 | ₹51,400.00 | **EXACT PARITY** |
| **Purchase Register Net ITC** | ₹16,200.00 | ₹16,200.00 | **EXACT PARITY** |
| **Active Posted Vouchers** | 7 vouchers | 7 vouchers | **EXACT PARITY** |
| **Verified Documents Count** | 10 documents | 10 documents | **EXACT PARITY** |
| **Rejected Duplicate Invoices** | 1 document | 1 document (`3c3ecc9e`) | **EXACT PARITY** |
| **Filed Statutory Returns** | 0 filed | 0 filed (1 voided) | **EXACT PARITY** |
| **Discrepancies (Q2 Period)** | 1 HIGH (₹18,000) | 1 HIGH (₹18,000) | **EXACT PARITY** |
| **Discrepancies (All Available)** | 1 HIGH + 1 MEDIUM | 1 HIGH + 1 MEDIUM | **EXACT PARITY** |

---

## 5. Verification Sign-Off

1. **Automated Unit & Integration Test Suites:**
   - `tests/test_multi_client_isolation_round4.py` — **PASSED** (3/3)
   - `tests/test_hsn_table12_all_periods.py` — **PASSED** (1/1)
   - `tests/test_payment_voucher_isolated.py` — **PASSED** (1/1)
   - `tests/test_alert_rules_regression.py` — **PASSED** (1/1)
   - `tests/test_filing_dialog_period_selection.py` — **PASSED** (2/2)
   - `tests/test_note_cdnr_by_recipient_gstin.py` — **PASSED** (2/2)
   - `tests/test_gst_parity_round3_e2e.py` — **PASSED** (1/1)
   - `tests/test_accounting_draft_bridge.py` — **PASSED** (15/15)
2. **Frontend Production Build:**
   - `npm run build` executed successfully (`vite v6.4.3`, 0 compile errors).
3. **Database Integrity:**
   - Ran `backend/scripts/integrity_check.py`: C-1071 ledger output tax ₹51,400.00, input tax ₹16,200.00, GSTR-3B cash payable ₹35,200.00 confirmed clean across all tenants.

All items F1 through F11 are fully resolved, committed, and ready for production merging.
