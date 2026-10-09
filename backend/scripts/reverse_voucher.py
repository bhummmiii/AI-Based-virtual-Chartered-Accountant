"""
Reverse Voucher Script (G8 Data Helper).
Safely reverses a posted accounting voucher or journal entry for a client:
- Preserves full audit trail (marks original as reversed, sets reversal reason and timestamp)
- Generates an offsetting balanced reversal entry
- Reverses linked AccountingRecord if present
- Default mode is DRY-RUN
- --apply requires --client-id and --voucher-ref

Usage:
  python reverse_voucher.py --client-id <CLIENT_ID_OR_CODE> --voucher-ref <REF> [--reason <REASON>]
  python reverse_voucher.py --client-id <CLIENT_ID_OR_CODE> --voucher-ref <REF> --apply
"""

import sys
import os
import io
import argparse
import uuid
from decimal import Decimal
from datetime import datetime, timezone, date
from typing import Optional

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.client import Client
from app.models.user import User
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.accounting_record import AccountingRecord
from app.models.chart_of_accounts import ChartOfAccounts


def find_client(db: Session, identifier: str) -> Optional[Client]:
    """Find client by UUID or client_code."""
    try:
        u_id = uuid.UUID(identifier)
        c = db.query(Client).filter(Client.id == u_id).first()
        if c:
            return c
    except ValueError:
        pass

    return db.query(Client).filter(Client.client_code.ilike(identifier.strip())).first()


def reverse_voucher(
    db: Session,
    client: Client,
    voucher_ref: str,
    reason: str = "Statutory voucher reversal",
    apply: bool = False,
) -> bool:
    """Find and reverse a voucher by voucher reference or entry number."""
    print(f"\n=======================================================")
    print(f"Reversing Voucher for Client: {client.company_name} ({client.client_code})")
    print(f"Target Voucher Reference: {voucher_ref}")
    print(f"Reversal Reason: {reason}")
    print(f"Execution Mode: {'APPLY (COMMITTING CHANGES)' if apply else 'DRY RUN (NO WRITES)'}")
    print(f"=======================================================")

    clean_ref = voucher_ref.strip()

    # Search for JournalEntry
    je = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.client_id == client.id,
            (JournalEntry.entry_number == clean_ref) | (JournalEntry.reference_number == clean_ref),
        )
        .first()
    )

    ar = None
    if not je:
        # Check AccountingRecord
        ar = (
            db.query(AccountingRecord)
            .filter(
                AccountingRecord.client_id == client.id,
                AccountingRecord.reference_number == clean_ref,
            )
            .first()
        )
        if ar and ar.journal_entry:
            je = ar.journal_entry

    if not je and not ar:
        print(f"[ERROR] No voucher or journal entry found for client matching reference '{clean_ref}'.")
        return False

    if je:
        if je.is_reversed or je.status == "reversed":
            print(f"[IDEMPOTENT] JournalEntry #{je.entry_number} is ALREADY REVERSED.")
            if je.reversal_entry_id:
                print(f"  Linked Reversal Entry ID: {je.reversal_entry_id}")
            if je.reversal_reason:
                print(f"  Recorded Reversal Reason: {je.reversal_reason}")
            return True

        print(f"\nFound JournalEntry #{je.entry_number} (ID: {je.id}):")
        print(f"  Date:       {je.entry_date}")
        print(f"  Type:       {je.entry_type}")
        print(f"  Status:     {je.status}")
        print(f"  Total Dr:   ₹{je.total_debit:,.2f}")
        print(f"  Total Cr:   ₹{je.total_credit:,.2f}")
        print(f"  Narration:  {je.narration}")
        print("  Current Lines:")
        for idx, line in enumerate(je.lines):
            acc_name = line.account.account_name if line.account else "Unknown Account"
            code = line.account.account_code if line.account else "—"
            print(f"    Line {idx+1}: [{code}] {acc_name:30s} | Dr: ₹{line.debit_amount:,.2f} | Cr: ₹{line.credit_amount:,.2f}")

        print("\nProposed Offsetting Reversal Lines:")
        for idx, line in enumerate(je.lines):
            acc_name = line.account.account_name if line.account else "Unknown Account"
            code = line.account.account_code if line.account else "—"
            print(f"    Rev {idx+1}:  [{code}] {acc_name:30s} | Dr: ₹{line.credit_amount:,.2f} | Cr: ₹{line.debit_amount:,.2f}")

        if not apply:
            print("\n[DRY RUN] No changes were written. Re-run with --apply to commit reversal.")
            return True

        # Generate Reversal Entry
        rev_entry_num = f"REV-{je.entry_number}"
        existing_rev = db.query(JournalEntry).filter(
            JournalEntry.client_id == client.id,
            JournalEntry.entry_number == rev_entry_num,
        ).first()
        if existing_rev:
            rev_entry_num = f"REV-{je.entry_number}-{uuid.uuid4().hex[:6].upper()}"

        rev_je = JournalEntry(
            id=uuid.uuid4(),
            client_id=client.id,
            document_id=je.document_id,
            entry_number=rev_entry_num,
            entry_date=date.today(),
            entry_type="reversal",
            status="posted",
            is_reversed=False,
            narration=f"Reversal of #{je.entry_number}: {reason}",
            reference_number=je.entry_number,
            total_debit=je.total_credit,
            total_credit=je.total_debit,
            is_balanced=True,
            counterparty_name=je.counterparty_name,
            counterparty_gstin=je.counterparty_gstin,
            voucher_template=je.voucher_template,
        )
        db.add(rev_je)
        db.flush()

        for idx, line in enumerate(je.lines):
            rev_line = JournalEntryLine(
                id=uuid.uuid4(),
                journal_entry_id=rev_je.id,
                line_number=idx + 1,
                account_id=line.account_id,
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount,
                description=f"Reversal of line {line.line_number} on #{je.entry_number}",
                party_name=line.party_name,
                party_gstin=line.party_gstin,
                tax_head=line.tax_head,
                tax_rate=line.tax_rate,
            )
            db.add(rev_line)

        # Update original entry audit trail
        je.is_reversed = True
        je.status = "reversed"
        je.reversal_entry_id = rev_je.id
        je.reversal_reason = reason

        # Reverse linked AccountingRecord if present
        if je.accounting_record_id:
            ar_rec = db.query(AccountingRecord).filter(AccountingRecord.id == je.accounting_record_id).first()
            if ar_rec:
                ar_rec.status = "reversed"
        elif ar:
            ar.status = "reversed"

        db.commit()
        print(f"\n[SUCCESS] Voucher #{je.entry_number} successfully reversed.")
        print(f"  Created Reversal Journal Entry: #{rev_je.entry_number} (ID: {rev_je.id})")
        return True

    elif ar:
        # AccountingRecord without JournalEntry
        if ar.status == "reversed":
            print(f"[IDEMPOTENT] AccountingRecord #{ar.reference_number} is ALREADY REVERSED.")
            return True

        print(f"\nFound AccountingRecord #{ar.reference_number} (ID: {ar.id}):")
        print(f"  Date:     {ar.transaction_date}")
        print(f"  Type:     {ar.voucher_type}")
        print(f"  Debit:    ₹{ar.debit:,.2f}")
        print(f"  Credit:   ₹{ar.credit:,.2f}")

        if not apply:
            print("\n[DRY RUN] No changes were written. Re-run with --apply to commit reversal.")
            return True

        # Create offsetting accounting record
        rev_ar = AccountingRecord(
            id=uuid.uuid4(),
            client_id=client.id,
            transaction_date=date.today(),
            voucher_type=ar.voucher_type,
            description=f"Reversal of {ar.reference_number}: {reason}",
            debit=ar.credit,
            credit=ar.debit,
            category=ar.category,
            document_id=ar.document_id,
            status="posted",
            reference_number=f"REV-{ar.reference_number}",
        )
        ar.status = "reversed"
        db.add(rev_ar)
        db.commit()
        print(f"\n[SUCCESS] AccountingRecord #{ar.reference_number} marked as reversed and offset posted.")
        return True

    return False


def main():
    parser = argparse.ArgumentParser(description="Reverse a posted voucher with audit trail.")
    parser.add_argument("--client-id", required=True, help="Client UUID or Client Code (e.g. C-1071)")
    parser.add_argument("--voucher-ref", required=True, help="Voucher reference number or entry number (e.g. PMT-2026-0001)")
    parser.add_argument("--reason", default="Statutory voucher reversal", help="Reason for reversal")
    parser.add_argument("--apply", action="store_true", help="Commit reversal changes (default is dry-run)")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        client = find_client(db, args.client_id)
        if not client:
            print(f"[ERROR] Client '{args.client_id}' not found.")
            sys.exit(1)

        success = reverse_voucher(
            db=db,
            client=client,
            voucher_ref=args.voucher_ref,
            reason=args.reason,
            apply=args.apply,
        )
        if not success:
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
