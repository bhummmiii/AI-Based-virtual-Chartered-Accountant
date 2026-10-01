"""
Cleanup Polluted Data Script (D7)
=================================
Remedies historical test pollution across both Journal Entries and Accounting Records:
1. Orphan voucher SV-2026-0001 (Ref NEG/0001, missing source document)
2. Negative test voucher PV-2026-0001 (Ref NEG/0002)
3. Corresponding AccountingRecord entries for NEG/0001 and NEG/0002 (synced to 'reversed')
4. Source documents for polluted records marked as 'rejected' / voided
5. Bogus filing record 2026-09 GSTR-3B (Taxable Rs. 7,00,00,000, Tax Rs. 0.00)

Multi-Client Safe (Rule R10):
- Accepts --client-id, --client-code, or --gstin.

Usage:
  python backend/scripts/cleanup_polluted_data.py --dry-run --client-id <CLIENT_UUID>
  python backend/scripts/cleanup_polluted_data.py --apply --client-id <CLIENT_UUID>
"""

import os
import sys
import argparse
import uuid
from typing import Optional, List

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.client import Client
from app.models.journal_entry import JournalEntry
from app.models.accounting_record import AccountingRecord
from app.models.uploaded_document import UploadedDocument
from app.models.gst_record import GSTRecord


def run_cleanup(
    client_id: Optional[uuid.UUID] = None,
    gstin: Optional[str] = None,
    client_code: Optional[str] = None,
    dry_run: bool = True,
) -> int:
    db: Session = SessionLocal()
    mode_str = "[DRY-RUN]" if dry_run else "[APPLY]"
    print("=" * 80)
    print(f"      FINLEDGER AI — DATA CLEANUP & AUDIT SYNC SCRIPT {mode_str}")
    print("=" * 80)

    try:
        q = db.query(Client)
        if client_id:
            q = q.filter(Client.id == client_id)
        elif gstin:
            q = q.filter(Client.gst_number == gstin.strip())
        elif client_code:
            q = q.filter(Client.client_code == client_code.strip())
        else:
            print("[ERROR] You must specify --client-id, --client-code, or --gstin (Multi-Client Safety Rule R10).")
            return 1

        client = q.first()
        if not client:
            print(f"[ERROR] Target client not found matching filters (id={client_id}, gstin={gstin}, code={client_code})")
            return 1

        print(f"\nTarget Client: {client.company_name} ({client.client_code} | GSTIN: {client.gst_number})")

        # 1. Target Vouchers (Journal Entries)
        target_vouchers = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client.id,
                JournalEntry.reference_number.in_(["NEG/0001", "NEG/0002"]),
            )
            .all()
        )

        print(f"\n[1] Target Journal Entries ({len(target_vouchers)} found):")
        for v in target_vouchers:
            print(f"    - Voucher #{v.entry_number} (Ref: {v.reference_number}, Status: {v.status}, is_reversed: {v.is_reversed})")

        # 2. Target Accounting Records
        ar_ids = [v.accounting_record_id for v in target_vouchers if v.accounting_record_id]
        target_records = (
            db.query(AccountingRecord)
            .filter(
                AccountingRecord.client_id == client.id,
                (
                    AccountingRecord.id.in_(ar_ids)
                    | AccountingRecord.reference_number.in_(["NEG/0001", "NEG/0002"])
                ),
            )
            .all()
        )

        print(f"\n[2] Target Accounting Records ({len(target_records)} found):")
        for ar in target_records:
            print(f"    - Record #{ar.id} (Ref: {ar.reference_number}, Status: {ar.status}, Type: {ar.voucher_type})")

        # 3. Target Source Documents
        doc_ids = [ar.document_id for ar in target_records if ar.document_id]
        target_docs = (
            db.query(UploadedDocument)
            .filter(
                UploadedDocument.client_id == client.id,
                (
                    UploadedDocument.id.in_(doc_ids)
                    | UploadedDocument.invoice_number.in_(["NEG/0001", "NEG/0002"])
                ),
            )
            .all()
        )

        print(f"\n[3] Target Source Documents ({len(target_docs)} found):")
        for d in target_docs:
            print(f"    - Document #{d.id} (Invoice: {d.invoice_number}, Status: {d.status}, Category: {d.document_category})")

        # 4. Target Bogus Filing: 2026-09 GSTR-3B (Taxable 70000000)
        target_filings = (
            db.query(GSTRecord)
            .filter(
                GSTRecord.client_id == client.id,
                GSTRecord.gst_period == "2026-09",
                GSTRecord.taxable_amount >= 10000000,
            )
            .all()
        )

        print(f"\n[4] Target Bogus Filing Records ({len(target_filings)} found):")
        for f in target_filings:
            print(f"    - Filing #{f.id} (Period: {f.gst_period}, Type: {f.gst_type}, Taxable: Rs. {f.taxable_amount}, Status: {f.filing_status})")

        if dry_run:
            print("\n" + "-" * 80)
            print("DRY RUN COMPLETE: No changes were written to the database.")
            print("To apply changes, run: python backend/scripts/cleanup_polluted_data.py --apply --client-id " + str(client.id))
            print("-" * 80)
            return 0

        # ── Apply Remediation ────────────────────────────────────────────────
        print("\nApplying remediation actions...")

        # A. Void/Reverse Vouchers
        for v in target_vouchers:
            if v.status != "reversed" or not v.is_reversed:
                v.status = "reversed"
                v.is_reversed = True
                v.reversal_reason = "Section 7 automated audit cleanup of orphan/polluted negative test entry"
                print(f"    [APPLIED] Voucher {v.entry_number} ({v.reference_number}) marked as REVERSED.")

        # B. Sync Accounting Records to 'reversed'
        for ar in target_records:
            if ar.status != "reversed":
                ar.status = "reversed"
                ar.description = f"[REVERSED] Polluted test record {ar.reference_number} reversed during audit cleanup"
                print(f"    [APPLIED] Accounting Record {ar.id} ({ar.reference_number}) synced to REVERSED.")

        # C. Mark Source Documents as 'rejected'
        for d in target_docs:
            if d.status != "rejected":
                d.status = "rejected"
                print(f"    [APPLIED] Polluted Document {d.id} ({d.invoice_number}) marked as REJECTED.")

        # D. Void Bogus Filing Record
        for f in target_filings:
            if f.filing_status != "voided":
                f.filing_status = "voided"
                print(f"    [APPLIED] Bogus Filing {f.id} ({f.gst_period} {f.gst_type}) marked as VOIDED.")

        db.commit()
        print("\n" + "=" * 80)
        print("REMEDIATION COMMITTED SUCCESSFULLY. Audit trail preserved across both ledger layers.")
        print("=" * 80)
        return 0

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Cleanup polluted test data and sync accounting records (D7)")
    parser.add_argument("--client-id", type=str, default=None, help="Target Client UUID")
    parser.add_argument("--client-code", type=str, default=None, help="Target Client Code (e.g. C-1070)")
    parser.add_argument("--gstin", type=str, default=None, help="Target Client GSTIN")
    parser.add_argument("--apply", action="store_true", default=False, help="Apply remedies (default is dry-run mode)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview changes without modifying DB")

    args = parser.parse_args()
    dry_run = not args.apply

    c_id = None
    if args.client_id:
        try:
            c_id = uuid.UUID(args.client_id)
        except ValueError:
            print(f"[ERROR] Invalid UUID: {args.client_id}")
            sys.exit(1)

    exit_code = run_cleanup(
        client_id=c_id,
        gstin=args.gstin,
        client_code=args.client_code,
        dry_run=dry_run,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
