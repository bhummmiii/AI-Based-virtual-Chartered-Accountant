"""
Integrity Check Script — Read-Only Audit & Statutory Verification Report.
Scans database for:
1. Orphan vouchers (vouchers without source document or invalid reference).
2. Unposted verified invoices/notes.
3. Non-invoice documents wrongly posted.
4. Mathematical imbalances in General Ledger.
5. Ledger-vs-GST discrepancies for active clients.
"""

import os
import sys
import uuid
from decimal import Decimal
from datetime import date

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.gst_record import GSTRecord
from app.services.gst_reconciliation_service import GstReconciliationService


def run_integrity_audit():
    db = SessionLocal()
    print("=" * 80)
    print("           FINLEDGER AI — SYSTEM AUDIT & INTEGRITY REPORT")
    print("=" * 80)

    try:
        # ── 1. Check for Orphan Vouchers ─────────────────────────────────────
        print("\n[CHECK 1] Scanning for Orphan Vouchers...")
        all_jes = db.query(JournalEntry).filter(JournalEntry.status == "posted").all()
        orphan_vouchers = []
        for je in all_jes:
            if not je.document_id:
                orphan_vouchers.append((je, "Missing document_id"))
            else:
                doc = db.query(UploadedDocument).filter(UploadedDocument.id == je.document_id).first()
                if not doc:
                    orphan_vouchers.append((je, f"Referenced document {je.document_id} not found"))

        if orphan_vouchers:
            print(f"  [!] Found {len(orphan_vouchers)} orphan voucher(s):")
            for je, reason in orphan_vouchers:
                client = db.query(Client).filter(Client.id == je.client_id).first()
                c_name = client.company_name if client else str(je.client_id)
                print(f"      - {je.entry_number} (Ref: {je.reference_number}): {reason} [Client: {c_name}]")
        else:
            print("  [OK] No orphan vouchers detected. All posted vouchers link to valid documents.")

        # ── 2. Check for Unposted Verified Documents ─────────────────────────
        print("\n[CHECK 2] Scanning for Unposted Verified Invoices/Notes...")
        invoice_cats = {
            "sales_records", "purchase_records", "b2b_invoice",
            "b2c_invoice", "credit_note", "debit_note", "e_invoice"
        }
        verified_docs = db.query(UploadedDocument).filter(
            UploadedDocument.status == "verified",
            UploadedDocument.document_category.in_(invoice_cats),
        ).all()

        unposted_docs = []
        for d in verified_docs:
            has_je = db.query(JournalEntry).filter(
                JournalEntry.document_id == d.id,
                JournalEntry.status == "posted",
            ).first()
            if not has_je:
                unposted_docs.append(d)

        if unposted_docs:
            print(f"  [!] Found {len(unposted_docs)} unposted verified document(s):")
            for d in unposted_docs:
                print(f"      - Doc ID {d.id} (#{d.invoice_number or 'N/A'}, Cat: {d.document_category}, Amount: Rs. {d.amount})")
        else:
            print("  [OK] All verified invoices and notes have been posted to the general ledger.")

        # ── 3. Check for Wrongly Posted Non-Invoice Documents ────────────────
        print("\n[CHECK 3] Checking Non-Invoice Document Isolation (EWB, Challan, HSN)...")
        non_inv_cats = {"e_way_bill", "gst_challan", "hsn_sac"}
        wrongly_posted = []
        non_inv_docs = db.query(UploadedDocument).filter(
            UploadedDocument.document_category.in_(non_inv_cats)
        ).all()
        for d in non_inv_docs:
            has_je = db.query(JournalEntry).filter(
                JournalEntry.document_id == d.id,
                JournalEntry.status == "posted",
            ).first()
            if has_je:
                wrongly_posted.append((d, has_je))

        if wrongly_posted:
            print(f"  [!] Found {len(wrongly_posted)} non-invoice document(s) with posted vouchers:")
            for d, je in wrongly_posted:
                print(f"      - Doc ID {d.id} ({d.document_category}) -> Voucher {je.entry_number}")
        else:
            print("  [OK] Non-invoice documents are strictly isolated; 0 vouchers posted.")

        # ── 4. Check Double-Entry Equilibrium ────────────────────────────────
        print("\n[CHECK 4] Checking Double-Entry Equilibrium on all Journal Entries...")
        imbalanced = []
        for je in all_jes:
            dr = Decimal(str(je.total_debit or 0.00))
            cr = Decimal(str(je.total_credit or 0.00))
            if abs(dr - cr) > Decimal("0.001"):
                imbalanced.append((je, dr, cr))

        if imbalanced:
            print(f"  [!] Found {len(imbalanced)} imbalanced journal entry(ies):")
            for je, dr, cr in imbalanced:
                print(f"      - {je.entry_number}: Dr Rs. {dr} != Cr Rs. {cr} (Diff: Rs. {abs(dr - cr)})")
        else:
            print(f"  [OK] All {len(all_jes)} posted journal entries are strictly balanced (Dr == Cr).")

        # ── 5. Client GST vs Ledger Reconciliation Status ────────────────────
        print("\n[CHECK 5] Validating Ledger-to-GST Reconciliation per Active Client...")
        clients = db.query(Client).filter(Client.status == "active").all()
        admin_user = User(id=uuid.uuid4(), role="admin", email="audit@system.local", full_name="System Auditor")

        for c in clients:
            gstin_str = c.gst_number or "NO-GSTIN"
            print(f"\n  Client: {c.company_name} ({c.client_code} | GSTIN: {gstin_str})")
            user_ctx = admin_user

            try:
                g1 = GstReconciliationService.reconcile_gstr1(db, c.id, user_ctx)
                g2 = GstReconciliationService.reconcile_gstr2b(db, c.id, user_ctx)
                g3 = GstReconciliationService.generate_gstr3b(db, c.id, user_ctx)

                print(f"    GSTR-1 Outward : Ledger Output Tax Rs. {g1.total_outward_tax} | Reconciled: {g1.is_reconciled}")
                print(f"    GSTR-2B Inward : Ledger Input Tax  Rs. {g2.total_eligible_itc} | Reconciled: {g2.is_reconciled}")
                print(f"    GSTR-3B Cash   : Tax Payable in Cash Rs. {g3.tax_payable_in_cash} (IGST: {g3.cash_payable_igst}, CGST: {g3.cash_payable_cgst}, SGST: {g3.cash_payable_sgst})")
                print(f"    ITC C/Fwd      : Rs. {g3.excess_credit_carried_forward} (CGST: {g3.itc_carried_forward_cgst}, SGST: {g3.itc_carried_forward_sgst}, IGST: {g3.itc_carried_forward_igst})")
            except Exception as e:
                print(f"    [!] Reconciliation error for client: {e}")

        print("\n" + "=" * 80)
        print("                        AUDIT SCAN COMPLETE")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    run_integrity_audit()
