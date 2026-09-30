"""
Cleanup Polluted Data Script (Section 7)
Target: Client "Ankit public Ltd" (GSTIN: 27AABCF8939R1ZW).

Identifies and remedies historical test pollution:
1. Orphan voucher SV-2026-0001 (Ref NEG/0001, missing source document)
2. Negative test voucher PV-2026-0001 (Ref NEG/0002)
3. Bogus filing record 2026-09 GSTR-3B (Taxable Rs. 7,00,00,000, Tax Rs. 0.00)

Usage:
  python cleanup_polluted_data.py            # Defaults to --dry-run
  python cleanup_polluted_data.py --apply    # Executes non-destructive reversal/voiding
"""

import os
import sys
import argparse
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.gst_record import GSTRecord
from app.services.journal_entry_service import JournalEntryService


def main():
    parser = argparse.ArgumentParser(description="Cleanup polluted test data for Ankit public Ltd")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply remedies (default is dry-run mode)",
    )
    args = parser.parse_args()
    is_dry_run = not args.apply

    db = SessionLocal()
    print("=" * 80)
    print(f"      FINLEDGER AI — DATA CLEANUP SCRIPT [{'DRY RUN' if is_dry_run else 'APPLY MODE'}]")
    print("=" * 80)

    try:
        client = db.query(Client).filter(Client.gst_number == "27AABCF8939R1ZW").first()
        if not client:
            print("  [!] Client 'Ankit public Ltd' (27AABCF8939R1ZW) not found.")
            return

        print(f"\nTarget Client: {client.company_name} (ID: {client.id} | GSTIN: {client.gst_number})")

        # 1. Target Vouchers: SV-2026-0001 (NEG/0001) and PV-2026-0001 (NEG/0002)
        target_vouchers = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client.id,
                JournalEntry.reference_number.in_(["NEG/0001", "NEG/0002"]),
            )
            .all()
        )

        print(f"\n[1] Found {len(target_vouchers)} target voucher(s) for remediation:")
        for v in target_vouchers:
            print(f"    - Voucher #{v.entry_number} (Ref: {v.reference_number}, Status: {v.status}, Total: Rs. {v.total_debit})")

        # 2. Target Bogus Filing: 2026-09 GSTR-3B (Taxable 70000000)
        target_filings = (
            db.query(GSTRecord)
            .filter(
                GSTRecord.client_id == client.id,
                GSTRecord.gst_period == "2026-09",
                GSTRecord.taxable_amount >= 10000000,
            )
            .all()
        )

        print(f"\n[2] Found {len(target_filings)} bogus GST filing record(s) for remediation:")
        for f in target_filings:
            print(f"    - Filing #{f.id} (Period: {f.gst_period}, Type: {f.gst_type}, Taxable: Rs. {f.taxable_amount}, Status: {f.filing_status})")

        if is_dry_run:
            print("\n" + "-" * 80)
            print("DRY RUN COMPLETE: No changes were written to the database.")
            print("To apply changes, run: python cleanup_polluted_data.py --apply")
            print("-" * 80)
            return

        # ── Apply Remediation ────────────────────────────────────────────────
        print("\nApplying remediation actions...")

        # A. Void/Reverse Vouchers
        for v in target_vouchers:
            if v.status == "posted":
                v.status = "reversed"
                v.is_reversed = True
                v.reversal_reason = "Section 7 automated audit cleanup of orphan/polluted negative test entry"
                print(f"    [APPLIED] Voucher {v.entry_number} ({v.reference_number}) marked as REVERSED.")

        # B. Void Bogus Filing Record
        for f in target_filings:
            f.filing_status = "voided"
            print(f"    [APPLIED] Bogus Filing {f.id} ({f.gst_period} {f.gst_type}) marked as VOIDED.")

        db.commit()
        print("\n" + "=" * 80)
        print("REMEDIATION COMMITTED SUCCESSFULLY. Audit trail preserved.")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
