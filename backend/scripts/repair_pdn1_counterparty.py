"""
Repair Script: Reverse-and-repost PDN1 voucher with corrected counterparty (F2).
Fixes X3:
- Reverses existing PDN1 voucher (JV-2026-0002)
- Reposts replacement voucher with counterparty TN Raw Materials Ltd / 33AABCT1111E1Z6
- Corrects creditor sub-ledger line party and GSTIN
- Updates AccountingRecord description party
- Updates UploadedDocument metadata

Rules:
- Dry-run by default
- --apply requires --client-id
- Idempotent: running twice changes nothing the second time
- Supports --all-clients --dry-run
"""

import sys
import os
import argparse
import uuid
import json
from decimal import Decimal
from datetime import datetime, timezone, date

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts


def repair_pdn_for_client(db, client: Client, apply: bool = False) -> bool:
    print(f"\nProcessing Client: {client.company_name} ({client.client_code or ''} | ID: {client.id})")
    
    # 1. Locate PDN document
    pdn_doc = db.query(UploadedDocument).filter(
        UploadedDocument.client_id == client.id,
        UploadedDocument.document_category == "debit_note",
    ).first()

    if not pdn_doc:
        # Check by invoice number pattern
        pdn_doc = db.query(UploadedDocument).filter(
            UploadedDocument.client_id == client.id,
            UploadedDocument.invoice_number.ilike("%PDN%"),
        ).first()

    if not pdn_doc:
        print("  No debit note document found for this client.")
        return False

    # 2. Check existing vouchers for this document
    all_jes = db.query(JournalEntry).filter(
        JournalEntry.client_id == client.id,
        JournalEntry.document_id == pdn_doc.id,
    ).all()

    # Check if already repaired (idempotency check: has a reversal voucher and a replacement voucher with creditor party_gstin)
    has_reversal = any((je.entry_number or "").startswith("REV-") for je in all_jes)
    replacement = next((je for je in all_jes if not je.is_reversed and not (je.entry_number or "").startswith("REV-") and any(l.party_gstin == "33AABCT1111E1Z6" for l in je.lines)), None)
    if has_reversal and replacement:
        # Check if AccountingRecord description also needs the party label aligned
        acc_rec = db.query(AccountingRecord).filter(
            AccountingRecord.document_id == pdn_doc.id,
            AccountingRecord.client_id == client.id,
        ).first()
        if acc_rec and "Party: TN Raw Materials Ltd" not in (acc_rec.description or ""):
            if not apply:
                print("  [DRY-RUN] Will update AccountingRecord description to display Party: TN Raw Materials Ltd.")
                return True
            desc = acc_rec.description or ""
            if "Party: ABC Traders Pvt Ltd" in desc:
                acc_rec.description = desc.replace("Party: ABC Traders Pvt Ltd", "Party: TN Raw Materials Ltd")
            elif "Party:" in desc:
                import re
                acc_rec.description = re.sub(r"Party:\s*[^|]+", "Party: TN Raw Materials Ltd", desc)
            else:
                acc_rec.description = f"{desc} | Party: TN Raw Materials Ltd"
            db.commit()
            print("  Updated AccountingRecord description to Party: TN Raw Materials Ltd.")
            return True
        print(f"  [IDEMPOTENT] PDN voucher is already correctly repaired with TN Raw Materials Ltd (33AABCT1111E1Z6) (Voucher #{replacement.entry_number}).")
        return False

    # Find the original non-reversed voucher that needs correction
    original_je = next(
        (je for je in all_jes if not je.is_reversed and not (je.entry_number or "").startswith("REV-")),
        None
    )

    if not original_je:
        print("  No active unreversed voucher found to repair.")
        return False

    print(f"  Found original active voucher #{original_je.entry_number} (Ref: {original_je.reference_number}):")
    print(f"    Current header: party='{original_je.counterparty_name}', gstin='{original_je.counterparty_gstin}'")
    for l in original_je.lines:
        print(f"      Line {l.line_number}: {l.account.account_name} ({l.account.account_code}) Dr {l.debit_amount} Cr {l.credit_amount} | Party: {l.party_name} | GSTIN: {l.party_gstin}")

    print("\n  Proposed Repairs:")
    print(f"    1. Mark #{original_je.entry_number} as reversed (is_reversed=True).")
    rev_entry_num = f"REV-{original_je.entry_number}"
    print(f"    2. Post Reversal Voucher #{rev_entry_num} on date {original_je.entry_date}:")
    print("       Dr Purchase Return 10,000.00")
    print("       Dr Input IGST 1,800.00")
    print("       Cr Creditors 11,800.00")

    # Generate next entry number for reposted entry
    repost_entry_num = f"{original_je.entry_number}-CORR"
    print(f"    3. Post Replacement Voucher #{repost_entry_num} on date {original_je.entry_date}:")
    print("       Header: counterparty='TN Raw Materials Ltd', gstin='33AABCT1111E1Z6', template='T6'")
    print("       Dr Creditors 11,800.00 (Party: TN Raw Materials Ltd, GSTIN: 33AABCT1111E1Z6)")
    print("       Cr Purchase Return 10,000.00")
    print("       Cr Input IGST 1,800.00")
    print("    4. Update AccountingRecord description to display Party: TN Raw Materials Ltd.")
    print("    5. Update UploadedDocument metadata to record customer_gstin: 33AABCT1111E1Z6.")

    if not apply:
        print("\n  [DRY-RUN] No changes written. Run with --apply to commit.")
        return True

    # ── APPLY REPAIRS ───────────────────────────────────────────
    now_ts = datetime.now(timezone.utc)

    # 1. Create Reversal Voucher
    reversal_header = JournalEntry(
        client_id=client.id,
        accounting_record_id=None,
        document_id=pdn_doc.id,
        entry_number=rev_entry_num,
        entry_date=original_je.entry_date,
        entry_type="reversal",
        status="posted",
        narration=f"Reversal of {original_je.entry_number}. Reason: Correct counterparty to TN Raw Materials Ltd (F2)",
        reference_number=f"REV-{original_je.reference_number or original_je.entry_number}",
        total_debit=original_je.total_debit,
        total_credit=original_je.total_credit,
        is_balanced=True,
        posted_at=now_ts,
        posted_by_user_id=original_je.posted_by_user_id,
        is_reversed=False,
        counterparty_name=original_je.counterparty_name,
        counterparty_gstin=original_je.counterparty_gstin,
        voucher_template="T6",
    )
    db.add(reversal_header)
    db.flush()

    # Reversal lines: swap Dr and Cr, Debits first
    creditor_line = next((l for l in original_je.lines if l.debit_amount and l.debit_amount > Decimal("0")), None)
    ret_line = next((l for l in original_je.lines if (l.account.role if l.account else None) == "PURCHASE_RETURN" or (l.account and "5020" in l.account.account_code)), None)
    igst_line = next((l for l in original_je.lines if (l.account.role if l.account else None) == "INPUT_IGST" or (l.account and "1230" in l.account.account_code)), None)

    rev_line1 = JournalEntryLine(
        journal_entry_id=reversal_header.id,
        line_number=1,
        account_id=ret_line.account_id if ret_line else original_je.lines[1].account_id,
        debit_amount=Decimal("10000.00"),
        credit_amount=Decimal("0.00"),
        description="Reversal leg: Purchase Return adjustment",
    )
    rev_line2 = JournalEntryLine(
        journal_entry_id=reversal_header.id,
        line_number=2,
        account_id=igst_line.account_id if igst_line else original_je.lines[2].account_id,
        debit_amount=Decimal("1800.00"),
        credit_amount=Decimal("0.00"),
        description="Reversal leg: Input IGST Reversal",
        tax_head="igst",
        tax_rate=Decimal("18.00"),
    )
    rev_line3 = JournalEntryLine(
        journal_entry_id=reversal_header.id,
        line_number=3,
        account_id=creditor_line.account_id if creditor_line else original_je.lines[0].account_id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("11800.00"),
        description="Reversal leg: Creditor debit reversal",
        party_name=original_je.counterparty_name,
        party_gstin=original_je.counterparty_gstin,
    )
    db.add_all([rev_line1, rev_line2, rev_line3])

    # 2. Mark original as reversed and release accounting_record_id to replacement
    old_acc_rec_id = original_je.accounting_record_id
    original_je.accounting_record_id = None
    original_je.is_reversed = True
    original_je.reversal_entry_id = reversal_header.id
    original_je.reversal_reason = "Correct counterparty to TN Raw Materials Ltd (F2)"
    db.flush()

    # 3. Create Reposted Voucher
    repost_header = JournalEntry(
        client_id=client.id,
        accounting_record_id=old_acc_rec_id,
        document_id=pdn_doc.id,
        entry_number=repost_entry_num,
        entry_date=original_je.entry_date,
        entry_type="journal",
        status="posted",
        narration=f"JOURNAL Voucher | Ref: {original_je.reference_number} | Gross: ₹{original_je.total_debit} | Linked Document: {pdn_doc.id}",
        reference_number=original_je.reference_number,
        total_debit=original_je.total_debit,
        total_credit=original_je.total_credit,
        is_balanced=True,
        posted_at=now_ts,
        posted_by_user_id=original_je.posted_by_user_id,
        is_reversed=False,
        counterparty_name="TN Raw Materials Ltd",
        counterparty_gstin="33AABCT1111E1Z6",
        voucher_template="T6",
    )
    db.add(repost_header)
    db.flush()

    new_line1 = JournalEntryLine(
        journal_entry_id=repost_header.id,
        line_number=1,
        account_id=creditor_line.account_id if creditor_line else original_je.lines[0].account_id,
        debit_amount=Decimal("11800.00"),
        credit_amount=Decimal("0.00"),
        description="Debit Note debit to TN Raw Materials Ltd",
        party_name="TN Raw Materials Ltd",
        party_gstin="33AABCT1111E1Z6",
    )
    new_line2 = JournalEntryLine(
        journal_entry_id=repost_header.id,
        line_number=2,
        account_id=ret_line.account_id if ret_line else original_je.lines[1].account_id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("10000.00"),
        description="Purchase Return adjustment from TN Raw Materials Ltd",
    )
    new_line3 = JournalEntryLine(
        journal_entry_id=repost_header.id,
        line_number=3,
        account_id=igst_line.account_id if igst_line else original_je.lines[2].account_id,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("1800.00"),
        description="Input IGST Reversal (Debit Note)",
        tax_head="igst",
        tax_rate=Decimal("18.00"),
    )
    db.add_all([new_line1, new_line2, new_line3])

    # 4. Update AccountingRecord
    if original_je.accounting_record_id:
        acc_rec = db.query(AccountingRecord).filter(AccountingRecord.id == original_je.accounting_record_id).first()
        if acc_rec:
            # Replace party in description
            desc = acc_rec.description or ""
            if "Party: ABC Traders Pvt Ltd" in desc:
                acc_rec.description = desc.replace("Party: ABC Traders Pvt Ltd", "Party: TN Raw Materials Ltd")
            elif "Party:" in desc:
                import re
                acc_rec.description = re.sub(r"Party:\s*[^|]+", "Party: TN Raw Materials Ltd", desc)
            else:
                acc_rec.description = f"{desc} | Party: TN Raw Materials Ltd"

    # 5. Update UploadedDocument
    pdn_doc.customer = "TN Raw Materials Ltd"
    pdn_doc.vendor = "ABC Traders Pvt Ltd"
    try:
        curr_meta = json.loads(pdn_doc.metadata_ or "{}")
        if "fields" not in curr_meta:
            curr_meta["fields"] = {}
        curr_meta["fields"]["customer_gstin"] = "33AABCT1111E1Z6"
        curr_meta["fields"]["customer"] = "TN Raw Materials Ltd"
        curr_meta["fields"]["supplier_gstin"] = "27AABCA1234A1Z5"
        curr_meta["fields"]["supplier"] = "ABC Traders Pvt Ltd"
        pdn_doc.metadata_ = json.dumps(curr_meta)
    except Exception:
        pass

    db.commit()
    print(f"\n  Successfully applied reverse-and-repost repair for #{original_je.entry_number} -> #{repost_entry_num}.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Repair PDN1 voucher counterparty via reverse-and-repost.")
    parser.add_argument("--client-id", type=str, help="UUID of client to apply repairs to")
    parser.add_argument("--apply", action="store_true", help="Apply database changes (requires --client-id)")
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
            repair_pdn_for_client(db, client, apply=args.apply)
        elif args.all_clients:
            clients = db.query(Client).all()
            print(f"Found {len(clients)} client(s) to inspect.")
            for c in clients:
                repair_pdn_for_client(db, c, apply=False)
        else:
            print("Usage: python repair_pdn1_counterparty.py [--client-id <UUID>] [--apply | --dry-run | --all-clients]")
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
