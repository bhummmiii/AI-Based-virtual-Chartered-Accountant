"""
Repost Legacy Vouchers Script (D2)
=================================
Identifies posted vouchers whose source document has statutory tax but lines lack GST accounts.
Reverses the legacy voucher with an opposing journal entry and posts a new balanced voucher using
statutory templates T1-T6.
Preserves complete double-entry audit trail (voided/reversed pairs net to zero).

Usage:
    python backend/scripts/repost_legacy_vouchers.py --dry-run --client-id <CLIENT_UUID>
    python backend/scripts/repost_legacy_vouchers.py --apply --client-id <CLIENT_UUID>
    python backend/scripts/repost_legacy_vouchers.py --apply --all-clients
"""

import sys
import os
import argparse
import uuid
from decimal import Decimal
from typing import List, Dict, Tuple, Optional

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.client import Client
from app.models.user import User
from app.services.accounting_mapping_service import AccountingMappingService
from app.services.journal_entry_service import JournalEntryService
from app.schemas.journal_entry import JournalEntryCreate, JournalEntryLineCreate

GST_ROLES = {
    "OUTPUT_CGST", "OUTPUT_SGST", "OUTPUT_IGST",
    "INPUT_CGST", "INPUT_SGST", "INPUT_IGST",
}
GST_ACCOUNT_CODES = {
    "2110", "2120", "2130",  # Output GST (ICAI / Live)
    "1210", "1220", "1230",  # Input GST (ICAI / Live)
    "1060", "1070", "1080",  # Legacy / alternative input codes
    "2020", "2030", "2040",  # Legacy / alternative output codes
}


def is_legacy_voucher_missing_tax_lines(je: JournalEntry, db: Session) -> Tuple[bool, Optional[UploadedDocument], Decimal]:
    """
    Check if a posted JournalEntry is a legacy voucher whose source document has tax
    but whose lines do not touch any GST account.
    """
    if je.status != "posted" or je.entry_type == "reversal":
        return False, None, Decimal("0.00")

    doc = None
    if je.document_id:
        doc = db.query(UploadedDocument).filter(UploadedDocument.id == je.document_id).first()
    elif je.accounting_record_id:
        ar = db.query(AccountingRecord).filter(AccountingRecord.id == je.accounting_record_id).first()
        if ar and ar.document_id:
            doc = db.query(UploadedDocument).filter(UploadedDocument.id == ar.document_id).first()

    if not doc:
        return False, None, Decimal("0.00")

    doc_tax = Decimal(str(
        (doc.cgst or Decimal("0.00")) +
        (doc.sgst or Decimal("0.00")) +
        (doc.igst or Decimal("0.00")) +
        (doc.cess or Decimal("0.00"))
    ))
    if doc_tax <= Decimal("0.00"):
        return False, doc, Decimal("0.00")

    # Inspect lines
    has_gst_account = False
    for line in je.lines:
        if line.account:
            if line.account.role in GST_ROLES or line.account.account_code in GST_ACCOUNT_CODES:
                has_gst_account = True
                break

    if not has_gst_account:
        return True, doc, doc_tax

    return False, doc, doc_tax


def repost_legacy_vouchers(
    db: Session,
    client_id: Optional[uuid.UUID] = None,
    all_clients: bool = False,
    apply: bool = False,
):
    query = db.query(JournalEntry).filter(JournalEntry.status == "posted")
    if client_id:
        query = query.filter(JournalEntry.client_id == client_id)

    posted_jes = query.all()
    legacy_items: List[Tuple[JournalEntry, UploadedDocument, Decimal]] = []

    for je in posted_jes:
        is_legacy, doc, tax_amt = is_legacy_voucher_missing_tax_lines(je, db)
        if is_legacy and doc:
            legacy_items.append((je, doc, tax_amt))

    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"\n{'=' * 80}")
    print(f"FinLedger AI — Repost Legacy Vouchers [{mode_label}]")
    print(f"{'=' * 80}")
    if client_id:
        client = db.query(Client).filter(Client.id == client_id).first()
        client_name = client.company_name if client else "Unknown"
        print(f"Target Client: {client_name} (ID: {client_id})")
    else:
        print(f"Target Scope: All Clients ({len(posted_jes)} total posted vouchers scanned)")

    print(f"Found {len(legacy_items)} legacy vouchers missing statutory GST lines.\n")

    if not legacy_items:
        print("No legacy vouchers requiring reposting found.")
        print(f"{'=' * 80}\n")
        return

    # System user for audit trail
    system_user = db.query(User).filter(User.role.in_(["admin", "ca"])).first() or db.query(User).first()
    if not system_user:
        system_user = User(
            id=uuid.uuid4(),
            role="admin",
            full_name="FinLedger Statutory Repost Script",
            email="statutory-repost@finledger.local",
        )

    for idx, (je, doc, tax_amt) in enumerate(legacy_items, 1):
        client = db.query(Client).filter(Client.id == je.client_id).first()
        client_info = f"{client.company_name} ({client.client_code})" if client else str(je.client_id)
        
        # User for client authorization
        client_user = db.query(User).filter(User.id == client.user_id).first() if (client and client.user_id) else None
        acting_user = client_user or system_user

        print(f"[{idx}/{len(legacy_items)}] Voucher #{je.entry_number} (ID: {je.id})")
        print(f"   Client:       {client_info}")
        print(f"   Date:         {je.entry_date}")
        print(f"   Document:     #{doc.invoice_number or 'UNKNOWN'} (Category: {doc.document_category})")
        print(f"   Doc Gross:    INR {doc.amount} | Tax: INR {tax_amt}")
        print("   Current Lines (missing tax accounts):")
        for line in je.lines:
            acc_desc = f"{line.account.account_code} - {line.account.account_name}" if line.account else str(line.account_id)
            print(f"      {acc_desc:40s} | Dr INR {line.debit_amount:10.2f} | Cr INR {line.credit_amount:10.2f}")

        # Compute new statutory payload
        try:
            new_payload = AccountingMappingService.map_document_to_journal_entry(
                db=db,
                doc=doc,
                user=acting_user,
                allow_client_mismatch=True,
            )
            print("   Proposed Statutory Lines (T1-T6 with GST):")
            for line in new_payload.lines:
                acc = db.query(ChartOfAccounts).filter(ChartOfAccounts.id == line.account_id).first()
                acc_desc = f"{acc.account_code} - {acc.account_name}" if acc else str(line.account_id)
                print(f"      {acc_desc:40s} | Dr INR {line.debit_amount:10.2f} | Cr INR {line.credit_amount:10.2f}")
        except Exception as e:
            print(f"   [ERROR] Failed to map document to statutory journal: {e}")
            continue

        if apply:
            try:
                # 1. Post reversal of legacy voucher
                rev_lines = [
                    JournalEntryLineCreate(
                        account_id=l.account_id,
                        debit_amount=l.credit_amount,
                        credit_amount=l.debit_amount,
                        description=f"Reversal of line {l.id} on {je.entry_number}",
                    )
                    for l in je.lines
                ]
                rev_payload = JournalEntryCreate(
                    client_id=je.client_id,
                    document_id=je.document_id,
                    entry_date=je.entry_date,
                    entry_type="reversal",
                    narration=f"Reversal of legacy voucher {je.entry_number} for doc #{doc.invoice_number or ''}",
                    reference_number=je.entry_number,
                    lines=rev_lines,
                )
                rev_je = JournalEntryService.create_journal_entry(
                    db=db,
                    client_id=je.client_id,
                    payload=rev_payload,
                    user=acting_user,
                    auto_commit=False,
                )
                rev_je.status = "reversed"

                # Detach accounting record from legacy entry if linked
                ar_id = je.accounting_record_id
                if ar_id:
                    je.accounting_record_id = None
                je.status = "reversed"
                db.flush()

                # 2. Post new statutory voucher
                if ar_id:
                    new_payload.accounting_record_id = ar_id
                new_payload.reference_number = doc.invoice_number or je.reference_number
                new_payload.narration = f"Statutory voucher for #{doc.invoice_number or ''} (replaces legacy {je.entry_number})"

                new_je = JournalEntryService.create_journal_entry(
                    db=db,
                    client_id=je.client_id,
                    payload=new_payload,
                    user=acting_user,
                    auto_commit=False,
                )

                # Update accounting record reference if linked
                if ar_id:
                    ar = db.query(AccountingRecord).filter(AccountingRecord.id == ar_id).first()
                    if ar:
                        ar.reference_number = new_je.entry_number
                        ar.status = "posted"

                db.commit()
                print(f"   [SUCCESS] Reversal Entry #{rev_je.entry_number} posted (status: reversed).")
                print(f"   [SUCCESS] New Statutory Entry #{new_je.entry_number} posted (status: posted).\n")
            except Exception as e:
                db.rollback()
                print(f"   [FAILED] Error applying repost for voucher {je.entry_number}: {e}\n")
        else:
            print("   [DRY-RUN] No database modifications made. Run with --apply to execute.\n")

    print(f"{'=' * 80}")
    print(f"Completed {len(legacy_items)} voucher evaluations.")
    print(f"{'=' * 80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Repost legacy vouchers that lack statutory tax lines (D2)."
    )
    parser.add_argument(
        "--client-id",
        type=str,
        default=None,
        help="Target client UUID to repost vouchers for.",
    )
    parser.add_argument(
        "--all-clients",
        action="store_true",
        default=False,
        help="Allow reposting across all clients.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply changes to database. Default is dry-run mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode without modifying data (default).",
    )

    args = parser.parse_args()

    # Safety checks
    if args.apply and not args.client_id and not args.all_clients:
        print("[ERROR] Safety violation: --apply requires either --client-id <uuid> or --all-clients flag.")
        sys.exit(1)

    client_uuid = None
    if args.client_id:
        try:
            client_uuid = uuid.UUID(args.client_id)
        except ValueError:
            print(f"[ERROR] Invalid UUID format for --client-id: {args.client_id}")
            sys.exit(1)

    db = SessionLocal()
    try:
        repost_legacy_vouchers(
            db=db,
            client_id=client_uuid,
            all_clients=args.all_clients,
            apply=args.apply,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
