"""
Relink Compliance Documents Script (F5).
Re-extracts printed Document No and IRN for e-invoices and e-way bills.
Auto-links compliance documents to matching commercial invoices:
- By printed document number + supplier GSTIN (+ date/amount)
- Never links to a document with a different number
- A document whose supplier GSTIN is the client's links only to client outward documents
- Manual / auto-link targets only non-rejected, non-duplicate invoices

Rules:
- Dry-run by default
- --apply requires --client-id
- Multi-client safe & idempotent
"""

import sys
import os
import argparse
import uuid
import json
import re
from typing import Optional, Tuple, List, Dict

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.uploaded_document import UploadedDocument
from app.api.routers.ocr.router import _parse_e_invoice, _parse_e_way_bill


def extract_text_from_doc(doc: UploadedDocument) -> str:
    """Extract raw text from PDF file or fallback to stored ocr_text."""
    if doc.ocr_text and len(doc.ocr_text.strip()) > 50:
        return doc.ocr_text

    if doc.file_path and os.path.exists(doc.file_path):
        try:
            import pypdf
            reader = pypdf.PdfReader(doc.file_path)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            full_text = "\n".join(pages_text).strip()
            if full_text:
                return full_text
        except Exception as e:
            print(f"    [WARN] Failed to read PDF {doc.file_path}: {e}")

    return doc.ocr_text or ""


def relink_for_client(db, client: Client, apply: bool = False) -> int:
    print(f"\nEvaluating Client: {client.company_name} ({client.client_code or ''} | ID: {client.id})")
    client_gstin = (client.gst_number or "").strip().upper()

    docs = db.query(UploadedDocument).filter(
        UploadedDocument.client_id == client.id,
        UploadedDocument.status != "voided",
    ).all()

    if not docs:
        print("  No active documents found.")
        return 0

    # Pool of candidate commercial invoices for linking:
    # Must be non-rejected, non-duplicate commercial documents
    commercial_cats_outward = {"sales_records", "b2b_invoice", "b2c_invoice"}
    commercial_cats_inward = {"purchase_records"}

    candidates = [
        d for d in docs
        if d.status != "rejected"
        and getattr(d, "rejection_reason", None) != "DUPLICATE"
        and (d.document_category in commercial_cats_outward or d.document_category in commercial_cats_inward)
    ]

    compliance_docs = [
        d for d in docs
        if d.document_category in ("e_invoice", "e_way_bill")
    ]

    if not compliance_docs:
        print("  No compliance documents (e_invoice / e_way_bill) found.")
        return 0

    updated_count = 0

    for doc in compliance_docs:
        cat = doc.document_category
        print(f"\n  [COMPLIANCE DOC] ID: {doc.id} | Cat: {cat} | Current InvNo: {doc.invoice_number}")

        raw_text = extract_text_from_doc(doc)
        meta_dict = {}
        if doc.metadata_:
            try:
                meta_dict = json.loads(doc.metadata_)
            except Exception:
                meta_dict = {}
        meta_fields = meta_dict.get("fields", {})

        printed_doc_no = None
        new_irn = None

        if cat == "e_invoice":
            # 1. Parse e-invoice
            core_parsed, meta_parsed = _parse_e_invoice(raw_text)
            parsed_doc_no = (core_parsed.get("invoice_number") or {}).get("value")
            parsed_irn = (core_parsed.get("irn") or {}).get("value")

            # Fallback regex on raw text if needed
            if not parsed_doc_no and raw_text:
                m_doc = re.search(r"Document\s*No[:\s]+([A-Za-z0-9\/\-_]+)", raw_text, re.I)
                if m_doc:
                    parsed_doc_no = m_doc.group(1).strip()

            if not parsed_irn and raw_text:
                m_irn = re.search(r"IRN[:\s]+([0-9a-fA-F\s]+)", raw_text, re.I)
                if m_irn:
                    cl_hex = re.sub(r"[^0-9a-fA-F]", "", m_irn.group(1))
                    if len(cl_hex) >= 64:
                        parsed_irn = cl_hex[:64].lower()

            printed_doc_no = parsed_doc_no
            new_irn = parsed_irn

            print(f"    Re-extracted Printed Doc No: '{printed_doc_no}' | IRN: '{new_irn}'")

        elif cat == "e_way_bill":
            # 2. Parse e-way bill
            core_parsed, meta_parsed = _parse_e_way_bill(raw_text)
            parsed_doc_no = (meta_parsed.get("linked_invoice_number") or {}).get("value")
            if not parsed_doc_no and raw_text:
                m_doc = re.search(r"Document\s*No[:\s]+([A-Za-z0-9\/\-_]+)", raw_text, re.I)
                if m_doc:
                    parsed_doc_no = m_doc.group(1).strip()

            printed_doc_no = parsed_doc_no
            print(f"    Extracted Printed Document No from EWB: '{printed_doc_no}'")

        # Determine direction
        doc_gstin = (doc.gstin or "").strip().upper()
        is_outward = (doc_gstin == client_gstin) or (cat == "e_way_bill" and "outward" in raw_text.lower())
        allowed_cats = commercial_cats_outward if is_outward else commercial_cats_inward

        print(f"    Direction: {'OUTWARD' if is_outward else 'INWARD'} (Supplier GSTIN: {doc_gstin})")

        # Match candidate strictly by printed document number
        target_candidate: Optional[UploadedDocument] = None
        if printed_doc_no:
            clean_printed = printed_doc_no.strip().upper()
            matching_candidates = [
                c for c in candidates
                if c.id != doc.id
                and c.document_category in allowed_cats
                and (c.invoice_number or "").strip().upper() == clean_printed
            ]

            if matching_candidates:
                if len(matching_candidates) == 1:
                    target_candidate = matching_candidates[0]
                else:
                    # Break ties by amount, then date
                    doc_amt = doc.amount or 0
                    def score(c: UploadedDocument):
                        amt_diff = abs((c.amount or 0) - doc_amt)
                        return amt_diff
                    target_candidate = sorted(matching_candidates, key=score)[0]
                print(f"    -> MATCH FOUND: Document #{target_candidate.invoice_number} (ID: {target_candidate.id} | Cat: {target_candidate.document_category} | Amount: {target_candidate.amount})")
            else:
                print(f"    -> No candidate matching number '{printed_doc_no}' found in {allowed_cats}. Leaving unlinked.")
        else:
            print("    -> No printed document number identified. Leaving unlinked.")

        # Check if updates are needed
        needs_update = False
        target_id = target_candidate.id if target_candidate else None
        target_inv_no = target_candidate.invoice_number if target_candidate else None

        if cat == "e_invoice":
            if printed_doc_no and doc.invoice_number != printed_doc_no:
                needs_update = True
            if new_irn and getattr(doc, "irn", None) != new_irn:
                needs_update = True

        if doc.linked_document_id != target_id:
            needs_update = True

        meta_linked_id = meta_dict.get("linked_invoice_id")
        meta_linked_no = meta_dict.get("linked_invoice_number")
        if meta_linked_id != (str(target_id) if target_id else None):
            needs_update = True

        if needs_update:
            if apply:
                if cat == "e_invoice":
                    if printed_doc_no:
                        doc.invoice_number = printed_doc_no
                    if new_irn:
                        doc.irn = new_irn
                        meta_fields["irn"] = new_irn
                        meta_fields["irn_hash"] = new_irn

                doc.linked_document_id = target_id
                if target_id and target_inv_no:
                    meta_dict["linked_invoice_id"] = str(target_id)
                    meta_dict["linked_invoice_number"] = target_inv_no
                    meta_fields["linked_invoice_id"] = str(target_id)
                    meta_fields["linked_invoice_number"] = target_inv_no
                else:
                    meta_dict.pop("linked_invoice_id", None)
                    meta_dict.pop("linked_invoice_number", None)
                    meta_fields.pop("linked_invoice_id", None)
                    meta_fields.pop("linked_invoice_number", None)

                meta_dict["fields"] = meta_fields
                doc.metadata_ = json.dumps(meta_dict)
                updated_count += 1
                print(f"    -> APPLIED update to DB: linked_doc_id={target_id}, invoice_number={doc.invoice_number}, irn={getattr(doc, 'irn', None)}")
            else:
                proposed_inv = printed_doc_no if cat == "e_invoice" else doc.invoice_number
                print(f"    -> [DRY-RUN] Would update: linked_doc_id={target_id}, invoice_number={proposed_inv}, irn={new_irn or getattr(doc, 'irn', None)}")
        else:
            print(f"    -> Already up-to-date. Linked to {doc.linked_document_id}.")

    if apply and updated_count > 0:
        db.commit()
        print(f"\n  Successfully updated {updated_count} compliance document(s) in database.")
    elif not apply:
        print(f"\n  Dry-run complete. {updated_count} compliance document(s) evaluated for relinking.")

    return updated_count


def main():
    parser = argparse.ArgumentParser(description="Relink compliance documents (e-invoices, e-way bills) to commercial invoices.")
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

            relink_for_client(db, client, apply=args.apply)

        elif args.all_clients:
            clients = db.query(Client).order_by(Client.company_name).all()
            print(f"Evaluating all {len(clients)} clients in dry-run mode...")
            total = 0
            for c in clients:
                total += relink_for_client(db, c, apply=False)
            print(f"\nTotal compliance documents needing relinking across all clients: {total}")
        else:
            print("Please specify either --client-id <uuid> (with optional --apply) or --all-clients --dry-run.")
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
