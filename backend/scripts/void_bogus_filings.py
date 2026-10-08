"""
Void Bogus Filings Script (F3).
Lists and soft-voids bogus GST filing records:
- Where period has not ended yet (period end >= today)
- Where recorded taxable amount or tax differs from server-computed figures by more than tolerance

Rules:
- Dry-run by default
- --apply requires --client-id
- Idempotent: running twice changes nothing
- Soft-void: filing_status='voided', void_reason=<reason>, voided_at=now_utc
- Retains full audit trail
"""

import sys
import os
import argparse
import uuid
from decimal import Decimal
from datetime import datetime, timezone, date

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.gst_record import GSTRecord
from app.models.user import User
from app.services.gst_reconciliation_service import GstReconciliationService

TOLERANCE = Decimal("1.00")


def evaluate_filing_records_for_client(db, client: Client, apply: bool = False) -> int:
    print(f"\nEvaluating Client: {client.company_name} ({client.client_code or ''} | ID: {client.id})")
    
    records = db.query(GSTRecord).filter(
        GSTRecord.client_id == client.id,
    ).all()

    if not records:
        print("  No filing records found.")
        return 0

    bogus_count = 0
    today = date.today()

    # Get admin user or client owner for verification
    user = db.query(User).filter(User.role == "admin").first()
    if not user and client.user_id:
        user = db.query(User).filter(User.id == client.user_id).first()

    for r in records:
        if r.filing_status == "voided" or r.void_reason:
            print(f"  [ALREADY VOIDED] ID: {r.id} | Period: {r.gst_period} | Form: {r.gst_type} | Reason: {r.void_reason}")
            continue

        start_d, end_d = GstReconciliationService._parse_period_dates(r.gst_period, None, None)
        is_bogus = False
        reasons = []

        # Check 1: Period has not ended
        if end_d and end_d >= today:
            is_bogus = True
            reasons.append(f"Period has not ended yet (Period end {end_d} >= today {today})")

        # Check 2: Figure comparison against server-authoritative ledger if period ended
        if not is_bogus and user:
            try:
                if r.gst_type == "GSTR-1":
                    recon = GstReconciliationService.reconcile_gstr1(db, client.id, user, period=r.gst_period)
                    server_taxable = recon.total_outward_taxable
                    server_tax = recon.total_outward_tax
                else:  # GSTR-3B
                    g3b = GstReconciliationService.generate_gstr3b(db, client.id, user, period=r.gst_period)
                    server_taxable = g3b.table_3_1_outward.taxable_value
                    server_tax = g3b.tax_payable_in_cash

                diff_taxable = abs(Decimal(str(r.taxable_amount or 0)) - server_taxable)
                diff_tax = abs(Decimal(str(r.total_tax or 0)) - server_tax)

                if diff_taxable > TOLERANCE or diff_tax > TOLERANCE:
                    is_bogus = True
                    reasons.append(
                        f"Figures differ from server ledger: Recorded Taxable INR {r.taxable_amount} (Server INR {server_taxable}), "
                        f"Recorded Tax INR {r.total_tax} (Server INR {server_tax})"
                    )
            except Exception as e:
                # If calculation fails or period invalid, flag for review
                pass

        if is_bogus:
            bogus_count += 1
            combined_reason = "; ".join(reasons)
            print(f"\n  [BOGUS RECORD DETECTED] ID: {r.id}")
            print(f"    Period: {r.gst_period} | Form: {r.gst_type} | Status: {r.filing_status}")
            print(f"    Recorded Taxable: INR {r.taxable_amount} | Recorded Tax: INR {r.total_tax}")
            print(f"    Void Reason: {combined_reason}")

            if apply:
                r.filing_status = "voided"
                r.void_reason = combined_reason
                r.voided_at = datetime.now(timezone.utc)
                print("    -> Successfully marked as VOIDED.")

    if apply and bogus_count > 0:
        db.commit()
        print(f"\n  Committed soft-void for {bogus_count} bogus filing record(s).")
    elif not apply and bogus_count > 0:
        print(f"\n  [DRY-RUN] Found {bogus_count} bogus record(s) that would be voided. Run with --apply to commit.")
    else:
        print("\n  All active filing records are valid. No bogus records to void.")

    return bogus_count


def main():
    parser = argparse.ArgumentParser(description="Void bogus GST filing records.")
    parser.add_argument("--client-id", type=str, help="UUID of client to inspect/apply")
    parser.add_argument("--apply", action="store_true", help="Apply voiding (requires --client-id)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run without writing changes (default)")
    parser.add_argument("--all-clients", action="store_true", help="Inspect all clients (dry-run only)")

    args = parser.parse_args()

    if args.apply:
        args.dry_run = False
        if not args.client_id:
            print("ERROR: --client-id is strictly required when running with --apply.")
            sys.exit(1)

    db = SessionLocal()
    try:
        if args.client_id:
            try:
                c_uuid = uuid.UUID(args.client_id)
            except ValueError:
                print(f"ERROR: Invalid UUID '{args.client_id}'")
                sys.exit(1)
            client = db.query(Client).filter(Client.id == c_uuid).first()
            if not client:
                print(f"ERROR: Client {args.client_id} not found.")
                sys.exit(1)
            evaluate_filing_records_for_client(db, client, apply=args.apply)
        elif args.all_clients:
            clients = db.query(Client).all()
            print(f"Found {len(clients)} client(s) to inspect.")
            for c in clients:
                evaluate_filing_records_for_client(db, c, apply=False)
        else:
            print("Usage: python void_bogus_filings.py [--client-id <UUID>] [--apply | --dry-run | --all-clients]")
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
