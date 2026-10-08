"""
Mark Duplicate Documents Script (F4).
Identifies duplicate uploads for a client (same document number + supplier GSTIN + document family).
Marks duplicate document (without a posted voucher, or later upload) as:
  status = "rejected"
  rejection_reason = "DUPLICATE"
Never touches the document with a posted voucher (e.g. b43c25ec).

Rules:
- Dry-run by default
- --apply requires --client-id
- Multi-client safe & idempotent
- Never marks e-invoices (companion documents) as duplicate
"""

import sys
import os
import argparse
import uuid
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Dict, Set

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry
from app.models.accounting_record import AccountingRecord


def get_doc_family(cat: str) -> str:
    cat = (cat or "").lower().strip()
    if cat in ("sales_records", "b2b_invoice", "b2c_invoice"):
        return "sales"
    elif cat in ("purchase_records",):
        return "purchase"
    elif cat in ("credit_note",):
        return "credit_note"
    elif cat in ("debit_note",):
        return "debit_note"
    return cat


def evaluate_duplicates_for_client(db, client: Client, apply: bool = False) -> int:
    print(f"\nEvaluating Client: {client.company_name} ({client.client_code or ''} | ID: {client.id})")

    # Exclude compliance docs and e-invoices (which are companion documents, not duplicates)
    excluded_cats = {"e_way_bill", "gst_challan", "hsn_sac", "e_invoice"}

    docs = db.query(UploadedDocument).filter(
        UploadedDocument.client_id == client.id,
        UploadedDocument.status != "voided",
    ).all()

    if not docs:
        print("  No active documents found.")
        return 0

    # Build posted documents set
    posted_jes = db.query(JournalEntry).filter(
        JournalEntry.client_id == client.id,
        JournalEntry.status == "posted",
        JournalEntry.is_reversed == False,
    ).all()
    posted_doc_ids: Set[uuid.UUID] = {je.document_id for je in posted_jes if je.document_id}

    for je in posted_jes:
        if je.accounting_record_id:
            rec = db.query(AccountingRecord).filter(AccountingRecord.id == je.accounting_record_id).first()
            if rec and rec.document_id:
                posted_doc_ids.add(rec.document_id)

    posted_records = db.query(AccountingRecord).filter(
        AccountingRecord.client_id == client.id,
        AccountingRecord.status == "posted",
    ).all()
    for ar in posted_records:
        if ar.document_id:
            posted_doc_ids.add(ar.document_id)

    # Group documents by (inv_num, gstin_key, doc_family)
    grouped: Dict[tuple, List[UploadedDocument]] = defaultdict(list)
    for d in docs:
        cat = (d.document_category or "").lower()
        if cat in excluded_cats:
            continue
        inv_num = (d.invoice_number or "").strip().upper()
        gstin_key = (d.gstin or "").strip().upper()
        if not inv_num or not gstin_key:
            continue
        fam = get_doc_family(cat)
        grouped[(inv_num, gstin_key, fam)].append(d)

    duplicate_candidates = 0
    updated_count = 0

    for (inv_num, gstin_key, fam), group in grouped.items():
        if len(group) <= 1:
            continue

        # Sort: document WITH posted voucher comes first; then by earliest created_at
        def sort_key(doc: UploadedDocument):
            has_voucher = 0 if doc.id in posted_doc_ids else 1
            created = doc.created_at or datetime.min.replace(tzinfo=timezone.utc)
            return (has_voucher, created)

        sorted_group = sorted(group, key=sort_key)
        original = sorted_group[0]
        duplicates = sorted_group[1:]

        print(f"\n  [DUPLICATE GROUP] #{inv_num} | GSTIN: {gstin_key} | Family: {fam}")
        print(f"    Original: {original.id} ({original.document_category}) | Posted: {original.id in posted_doc_ids} | Status: {original.status}")

        for dup in duplicates:
            duplicate_candidates += 1
            is_already_rejected = dup.status == "rejected" and dup.rejection_reason == "DUPLICATE"
            print(f"    Duplicate: {dup.id} ({dup.document_category}) | Posted: {dup.id in posted_doc_ids} | Status: {dup.status} | Reason: {dup.rejection_reason}")

            if is_already_rejected:
                print(f"      -> Already marked rejected as DUPLICATE. No change needed.")
            else:
                if apply:
                    # Safety check: NEVER reject a document with a posted voucher
                    if dup.id in posted_doc_ids:
                        print(f"      [SAFETY WARNING] Document {dup.id} has a posted voucher! Skipping.")
                        continue
                    dup.status = "rejected"
                    dup.rejection_reason = "DUPLICATE"
                    updated_count += 1
                    print(f"      -> APPLIED: Status set to 'rejected', rejection_reason set to 'DUPLICATE'.")
                else:
                    print(f"      -> [DRY-RUN] Would mark as rejected (reason: DUPLICATE).")

    if apply and updated_count > 0:
        db.commit()
        print(f"\n  Successfully updated {updated_count} duplicate document(s) in database.")
    elif not apply:
        print(f"\n  Dry-run complete. {duplicate_candidates} duplicate(s) evaluated.")

    return updated_count if apply else duplicate_candidates


def main():
    parser = argparse.ArgumentParser(description="Mark duplicate documents as rejected with reason DUPLICATE.")
    parser.add_argument("--client-id", type=str, default=None, help="Client UUID to evaluate")
    parser.add_argument("--all-clients", action="store_true", help="Evaluate all clients (dry-run only)")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database (requires --client-id)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Perform dry-run without writing")

    args = parser.parse_args()

    if args.apply and not args.client_id:
        print("Error: --apply requires an explicit --client-id <uuid>.")
        sys.exit(1)

    if args.apply and args.all_clients:
        print("Error: --apply cannot be used with --all-clients. Must target one client at a time.")
        sys.exit(1)

    db = SessionLocal()
    try:
        if args.client_id:
            try:
                cid = uuid.UUID(args.client_id)
            except ValueError:
                print(f"Invalid UUID: {args.client_id}")
                sys.exit(1)

            client = db.query(Client).filter(Client.id == cid).first()
            if not client:
                print(f"Client not found: {args.client_id}")
                sys.exit(1)

            evaluate_duplicates_for_client(db, client, apply=args.apply)

        elif args.all_clients:
            clients = db.query(Client).order_by(Client.company_name).all()
            print(f"Evaluating all {len(clients)} clients in dry-run mode...")
            total_candidates = 0
            for c in clients:
                total_candidates += evaluate_duplicates_for_client(db, c, apply=False)
            print(f"\nTotal duplicate candidates found across all clients: {total_candidates}")
        else:
            print("Please specify either --client-id <uuid> (with optional --apply) or --all-clients --dry-run.")
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
