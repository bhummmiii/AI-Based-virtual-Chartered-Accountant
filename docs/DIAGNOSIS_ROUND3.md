# Phase A — Round 3 Diagnosis Report (Defects E1–E11)

**Date:** 06-Oct-2026  
**Client Tested:** C-1071 (`oggy pvt ltd`, GSTIN `27AABCA1234A1Z5`, Maharashtra, Quarterly)  
**Database:** PostgreSQL (`ca_assistant_db`)  

---

## Executive Summary & Phase A Diagnostic Questions

### (a) Why the Ankit client earlier classified CN1 as CDNR with Mehta's GSTIN, but C-1071 shows CDNUR "Unregistered"
- **Code Reference:** `backend/app/services/gst_reconciliation_service.py:448-461` and `496`:
  ```python
  doc_g = (d.gstin or "").strip().upper()
  recipient_gstin = ""
  if meta_customer_gst and len(meta_customer_gst) == 15 and meta_customer_gst != client_gstin:
      recipient_gstin = meta_customer_gst
  elif (
      doc_g
      and len(doc_g) == 15
      and doc_g != client_gstin
      and doc_g != meta_supplier_gst
      and d.document_category not in ("b2c_invoice", "sales_records")
      and "unregistered" not in (d.customer or "").lower()
  ):
      recipient_gstin = doc_g

  has_gstin = bool(recipient_gstin and len(recipient_gstin) == 15)
  ...
  row_item.supply_type = "CDNR" if has_gstin else "CDNUR"
  ```
- **Root Cause & Live Evidence:**
  1. For the **Ankit client** (`70796fab-5319-4dfa-a760-36101d3db20c`), the client GSTIN is `27AABCF8939R1ZW`. In Ankit's uploaded `CN1` document, `d.metadata_["fields"]["customer_gstin"]` was populated with Mehta's GSTIN `27AAAPM5678B1Z2`. Thus `meta_customer_gst != client_gstin` was `True`, setting `recipient_gstin = "27AAAPM5678B1Z2"` and `supply_type = "CDNR"`.
  2. For **client C-1071** (`915b40bc-cfff-49e1-87ac-f79fa861c0e6`), the client's own GSTIN is `27AABCA1234A1Z5`. When `CN1_CREDIT_NOTE.pdf` (`fb1ce894-2dfb-40e9-b6ee-82e5be97b8a7`) was uploaded, `d.gstin` was stored as `27AABCA1234A1Z5` (the issuer's GSTIN), while `d.metadata_["fields"]` was empty `{}`.
  3. Consequently, in `gst_reconciliation_service.py`, `meta_customer_gst` was empty `""`, and `doc_g != client_gstin` evaluated to `False` (`27AABCA1234A1Z5 == 27AABCA1234A1Z5`).
  4. The service did **not** inspect the physical PDF text on disk (`Recipient (To) Mehta Enterprises ... GSTIN: 27AAAPM5678B1Z2`) nor did it fall back to the referenced original invoice (`Against Invoice ABC/26-27/001 dt 05-Jul-2026`).
  5. As a result, `recipient_gstin` became empty `""`, `has_gstin` became `False`, and line 496 classified CN1 as `CDNUR` ("Unregistered").

---

### (b) Which code path lets the "Log Filed Return" button and "Record Return Filing" create a record with free-typed amounts
- **Code Reference:**
  1. Frontend: `src/app/components/client/GstWorkspaceView.tsx:368-391`:
     ```typescript
     const taxableNum = parseFloat(filingTaxable) || ...;
     const taxNum = parseFloat(filingTax) || ...;
     const payload = {
       client_id: clientId,
       gst_period: filingPeriod,
       gst_type: filingForm,
       taxable_amount: taxableNum,
       ...
     };
     await fetch(`${base}/gst/records`, { method: "POST", body: JSON.stringify(payload) });
     ```
  2. Backend: `backend/app/api/routers/gst/router.py:288-315` (`create_gst_record`):
     ```python
     taxable_amount = payload.taxable_amount
     cgst = payload.cgst
     sgst = payload.sgst
     igst = payload.igst
     total_tax = payload.total_tax

     if taxable_amount is None or taxable_amount == Decimal("0.00"):
         # Only re-computed if client sent None or 0!
     ```
- **Root Cause & Live Evidence:**
  1. The backend endpoint accepted client-supplied `payload.taxable_amount` and `payload.total_tax` directly without authoritative server-side computation whenever the values were non-zero.
  2. The endpoint did not validate whether the filing period had ended (`period_end < today`).
  3. The endpoint did not validate whether the period frequency matched the client's `return_frequency` (quarterly client C-1071 was allowed to file for monthly period `2026-10`).
  4. On 2026-10-05, a record was saved with period `2026-10`, taxable `90,000,000.00`, tax `0.00`, and status `filed` (`id: e89e205d-f826-4728-92ef-09714fedc6ad`).

---

### (c) Which code selects the "parent commercial invoice" for e-invoice and e-way bill auto-link
- **Code Reference:**
  1. Backend OCR extraction: `backend/app/api/routers/ocr/router.py:2818-2820` and `2823-2845`:
     - In `_parse_e_invoice`, it directly called `_parse_invoice`. In `_parse_invoice`, the 64-character IRN hash matched first, storing the IRN string in `invoice_number` instead of the printed `Document No: ABC/26-27/002`.
     - In `_parse_e_way_bill`, `ewb_no` was stored in `invoice_number`, while `doc_no` was stored in `meta["linked_invoice_number"]`.
  2. Frontend linking dialog: `src/app/components/client/DocumentDetailModal.tsx:1615-1623`:
     ```typescript
     const commercialInvoices = useMemo(() => {
       return (allDocs || []).filter(
         (d) => d.id !== docId && ["sales_records", "purchase_records", "b2b_invoice", "b2c_invoice"].includes(d.document_category)
       );
     }, [allDocs, docId]);
     ```
- **Root Cause & Live Evidence:**
  1. There was no server-side or client-side automated document-linking engine during upload or processing that matched by `(document_number + supplier_gstin)`.
  2. Because `invoice_number` of `E1_e-Invoice_S2.pdf` was stored as the 64-char IRN `3025278422a1084f9e226a33d0527b65662e4c0a3c1d0b8a087f7d506021f2a4`, automated matching by invoice number failed.
  3. In `DocumentDetailModal.tsx`, the selection dropdown simply listed all sales/purchase documents without filtering by direction (client supplier vs recipient) or ranking by document number equality, resulting in manual mis-linking or arbitrary selection.
  4. Compliance documents (`e_invoice`, `e_way_bill`) were included in `unposted_eligible_categories` in `gst_reconciliation_service.py:1161`, causing `UNPOSTED_INVOICE` discrepancies to fire even when companion invoices were already posted.

---

### (d) Why PAYMENT vouchers are counted in HSN Table 12 and in the LEGACY_VOUCHER_NO_TAX_LINES discrepancy
- **Code Reference:**
  1. HSN Table 12: `backend/app/services/gst_reconciliation_service.py:1454-1603` (`get_gstr1_table_12_hsn_summary`):
     - The function iterated through all posted journal entries where `direction == "OUTWARD"` and `not has_purchase_lines`.
     - For payment voucher `JE PMT-2026-0001` (ref `26100012345678`, doc `GST_Challan_Q2.pdf`, amount ₹84,700), lines are `Dr 2150 GST Tax Payment Clearing` / `Cr 1020 Bank`.
     - Because it has no purchase accounts, the filter did not exclude it!
     - Because the challan has no line items, it fell back to line 1572: `hsn_code = str(d.hsn or "OTH").strip()` -> `"OTH"`!
     - It accumulated into HSN Table 12 as a junk row: `OTH / IGST 84,700 / 4 vouchers`.
  2. Legacy Voucher Discrepancy: `backend/app/services/gst_reconciliation_service.py:1272-1298`:
     - The check verified whether `doc_tax > 0` on the linked document.
     - For `GST_Challan_Q2.pdf`, `doc.amount = 84700.00` was treated as tax.
     - The code checked whether the voucher lines contained GST accounts `2110, 2120, 2130, 1210, 1220, 1230`.
     - Because payment voucher `JE PMT-2026-0001` correctly touches `2150` (Tax Clearing) and `1020` (Bank), `has_gst_line` was `False`.
     - The check fired a false **HIGH** discrepancy `LEGACY_VOUCHER_NO_TAX_LINES` on `JE PMT-2026-0001`, blocking return filing.

---

## Detailed Root Causes for Items E1–E11

### E1. GSTR-3B Cash Calculation and Negative ITC Heads
- **File & Line:** `backend/app/services/gst_reconciliation_service.py:948-950` and `983-987`.
- **Proof:** Live call to `generate_gstr3b(period='2026-Q2')` returns:
  `table_3_1_outward`: IGST 36,000, CGST 7,700, SGST 7,700 (Total 51,400).
  `table_4_net_itc`: IGST -1,800, CGST 9,000, SGST 9,000 (Total 16,200).
  `tax_payable_in_cash`: `33,400.00` (floored negative IGST at 0 and vanished 1,800).
  Correct statutory cash payable is `35,200.00` (`51,400 - 16,200 = 35,200`).

### E2. HSN Table 12 Extracted Outward Items Only
- **File & Line:** `backend/app/services/gst_reconciliation_service.py:1454-1603`.
- **Proof:** Table 12 currently includes non-sales vouchers (Payment Voucher `26100012345678` for GST Challan ₹84,700) and displays party name as fallback description.

### E3. CDNR vs CDNUR Note Classification
- **File & Line:** `backend/app/services/gst_reconciliation_service.py:448-461, 496`.
- **Proof:** CN1 for C-1071 had `d.gstin = 27AABCA1234A1Z5` (client GSTIN) and empty `fields` in metadata. Check failed `doc_g != client_gstin`, resolving to `CDNUR`.

### E4. Bogus Filing Records and Unguarded Path
- **File & Line:** `backend/app/api/routers/gst/router.py:288-315` and `GSTRecord` row `e89e205d-f826-4728-92ef-09714fedc6ad`.
- **Proof:** Querying `GSTRecord` for C-1071 returned 1 record: `2026-10 | GSTR-3B | taxable=90000000.00 | tax=0.00 | filed`.

### E5. Auto-Linking of E-Invoice and E-Way Bill
- **File & Line:** `backend/app/api/routers/ocr/router.py:2818` and `src/app/components/client/DocumentDetailModal.tsx:1615`.
- **Proof:** `doc.invoice_number` for `E1_e-Invoice_S2.pdf` is `3025278422a1084f9e226a33d0527b65662e4c0a3c1d0b8a087f7d506021f2a4` (IRN) instead of `ABC/26-27/002`.

### E6. Counterparty on Purchase-Side Notes
- **File & Line:** `backend/app/services/gst_reconciliation_service.py:590-620` (`reconcile_gstr2b`) and `JE JV-2026-0002`.
- **Proof:** In `reconcile_gstr2b`, PDN1 displayed `party_name = ABC Traders Pvt Ltd` and `party_gstin = 27AABCA1234A1Z5` (client's own name and GSTIN instead of TN Raw Materials Ltd `33AABCT1111E1Z6`).

### E7. Payment (Challan) Vouchers Isolated from GST Figures
- **File & Line:** `backend/app/services/gst_reconciliation_service.py:1272-1298, 1464-1471`.
- **Proof:** `detect_discrepancies(period=None)` reported `LEGACY_VOUCHER_NO_TAX_LINES` on `JE PMT-2026-0001` (doc `bf9154a5`, tax at risk 84,700).

### E8. Discrepancy Accuracy and Duplicate Handling
- **File & Line:** `backend/app/services/gst_reconciliation_service.py:1211, 1161`.
- **Proof:** `detect_discrepancies` on duplicate S1 reported `variance_amount = 118,000.00` (gross) instead of tax (`18,000.00`). E-invoice E1 raised `UNPOSTED_INVOICE`.

### E9. Filing Dialog Period & Statutory Figures
- **File & Line:** `src/app/components/client/GstWorkspaceView.tsx:325-350, 368-390`.
- **Proof:** Free-text inputs allow tampering; no guard against unselected "All Available" period.

### E10. Account Roles / Labels (4020 Sales Return)
- **File & Line:** `backend/app/services/chart_of_accounts_service.py:80-95`.
- **Proof:** Account 4020 has role `SALES_RETURN` (contra-revenue). Verified to reduce revenue in P&L and Trial Balance.

### E11. Governance Counters & Strips
- **File & Line:** `src/app/components/client/GstWorkspaceView.tsx:247-260`.
- **Proof:** `Filed` counted all records (including bogus/voided records), and `Verified` counted rejected duplicate documents.
