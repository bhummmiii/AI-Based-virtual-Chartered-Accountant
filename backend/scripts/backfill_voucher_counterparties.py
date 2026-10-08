"""
Backfill Voucher Counterparties & Template Script (F1)
======================================================
Backfills additive header columns on journal_entries:
- counterparty_name
- counterparty_gstin
- voucher_template (T1-T6, PAYMENT)

Multi-Client Safe (Rule R7/R8):
- Dry-run by default.
- Requires --client-id for --apply.
- Idempotent: re-running makes 0 changes.

Usage:
  python backend/scripts/backfill_voucher_counterparties.py --dry-run --client-id <CLIENT_UUID>
  python backend/scripts/backfill_voucher_counterparties.py --apply --client-id <CLIENT_UUID>
  python backend/scripts/backfill_voucher_counterparties.py --all-clients --dry-run
"""

import os
import sys
import re
import json
import argparse
import uuid
from typing import Optional, List, Dict, Any, Tuple

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.client import Client
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.uploaded_document import UploadedDocument
from app.models.accounting_record import AccountingRecord


def get_absolute_file_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    candidates = [
        path,
        os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), path),
        os.path.join(os.getcwd(), path),
        os.path.join(os.getcwd(), "backend", path),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


def extract_pdf_text(path: str) -> str:
    abs_p = get_absolute_file_path(path)
    if not abs_p:
        return ""
    try:
        import pypdf
        reader = pypdf.PdfReader(abs_p)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def resolve_counterparty_for_doc(
    doc: UploadedDocument,
    client: Client,
    db: Session,
) -> Tuple[str, Optional[str], str]:
    """
    Resolves (counterparty_name, counterparty_gstin, template) for a document.
    """
    client_gstin = (client.gst_number or "").strip().upper()
    client_name = (client.company_name or "").strip()
    cat = (doc.document_category or "").lower()

    meta = {}
    if doc.metadata_:
        try:
            meta = json.loads(doc.metadata_) if isinstance(doc.metadata_, str) else doc.metadata_
        except Exception:
            pass
    fields = meta.get("fields", {}) if isinstance(meta, dict) else {}
    def _val(k):
        v = fields.get(k)
        return v.get("value") if isinstance(v, dict) else v

    meta_cust_gst = str(_val("customer_gstin") or _val("buyer_gstin") or _val("recipient_gstin") or "").strip().upper()
    meta_supp_gst = str(_val("supplier_gstin") or _val("seller_gstin") or _val("vendor_gstin") or "").strip().upper()
    cust_name = str(_val("customer") or doc.customer or "").strip()
    vend_name = str(_val("vendor") or doc.vendor or "").strip()

    pdf_text = extract_pdf_text(doc.file_path)

    # 1. GST Challan
    if cat == "gst_challan":
        return "GST Tax Authority (Government Treasury)", None, "PAYMENT"

    # 2. Credit Note (outward sales return)
    if cat == "credit_note":
        recip_name = cust_name
        recip_gst = meta_cust_gst if meta_cust_gst != client_gstin else ""
        if (not recip_gst or len(recip_gst) != 15) and pdf_text:
            recip_m = re.search(
                r"Recipient\s*(?:\(To\))?[\s\r\n]+([A-Za-z0-9 .,&\'\-]{3,50})[\s\S]*?GSTIN[:\s]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])",
                pdf_text,
                re.I,
            )
            if recip_m:
                cand_name = recip_m.group(1).strip()
                cand_gst = recip_m.group(2).strip().upper()
                if cand_gst != client_gstin:
                    recip_gst = cand_gst
                    if cand_name:
                        recip_name = cand_name

        if (not recip_gst or len(recip_gst) != 15):
            orig_inv = str(_val("original_invoice_number") or _val("linked_invoice_number") or "").strip()
            if not orig_inv and pdf_text:
                m_ref = re.search(r"Against Invoice\s+([A-Za-z0-9\/\-_]+)", pdf_text, re.I)
                if m_ref:
                    orig_inv = m_ref.group(1).strip()
            if orig_inv:
                orig_doc = (
                    db.query(UploadedDocument)
                    .filter(
                        UploadedDocument.client_id == doc.client_id,
                        UploadedDocument.invoice_number == orig_inv,
                    )
                    .first()
                )
                if orig_doc:
                    o_name, o_gst, _ = resolve_counterparty_for_doc(orig_doc, client, db)
                    if o_gst and o_gst != client_gstin:
                        recip_gst = o_gst
                        if o_name:
                            recip_name = o_name

        return recip_name or "Customer", (recip_gst if len(recip_gst) == 15 else None), "T3"

    # 3. Debit Note
    if cat == "debit_note":
        # Check if purchase return (client issued to supplier)
        is_client_issuer = (
            (doc.gstin and doc.gstin.strip().upper() == client_gstin)
            or (client_name and vend_name and client_name.lower() in vend_name.lower())
        )
        if is_client_issuer:
            # Supplier is the recipient
            supp_name = cust_name
            supp_gst = meta_cust_gst if meta_cust_gst != client_gstin else ""
            if (not supp_gst or len(supp_gst) != 15) and pdf_text:
                recip_m = re.search(
                    r"Recipient\s*(?:\(To\))?[\s\r\n]+([A-Za-z0-9 .,&\'\-]{3,50})[\s\S]*?GSTIN[:\s]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])",
                    pdf_text,
                    re.I,
                )
                if recip_m:
                    cand_name = recip_m.group(1).strip()
                    cand_gst = recip_m.group(2).strip().upper()
                    if cand_gst != client_gstin:
                        supp_gst = cand_gst
                        if cand_name:
                            supp_name = cand_name
            return supp_name or "Supplier", (supp_gst if len(supp_gst) == 15 else None), "T6"
        else:
            return vend_name or "Vendor", (meta_supp_gst or doc.gstin or None), "T4"

    # 4. Purchase Records
    if cat in ("purchase_records", "purchase_invoice"):
        supp_name = vend_name
        supp_gst = meta_supp_gst or (doc.gstin if doc.gstin != client_gstin else "")
        return supp_name or "Vendor", (supp_gst if len(supp_gst) == 15 else None), "T2"

    # 5. Sales Records (B2B, B2C)
    if cat in ("sales_records", "b2b_invoice", "b2c_invoice"):
        c_gst = meta_cust_gst if meta_cust_gst != client_gstin else ""
        return cust_name or "Customer", (c_gst if len(c_gst) == 15 else None), "T1"

    # Fallback
    party = cust_name or vend_name or "Counterparty"
    gst = meta_cust_gst or meta_supp_gst or None
    if gst == client_gstin:
        gst = None
    return party, gst, "T1"


def backfill_client(db: Session, client: Client, dry_run: bool = True) -> int:
    jes = (
        db.query(JournalEntry)
        .filter(JournalEntry.client_id == client.id)
        .order_by(JournalEntry.entry_date.asc())
        .all()
    )

    print(f"\nProcessing Client: {client.company_name} ({client.client_code} | ID: {client.id})")
    print(f"Total Vouchers: {len(jes)}")

    changed = 0
    for je in jes:
        doc = None
        if je.document_id:
            doc = db.query(UploadedDocument).filter(UploadedDocument.id == je.document_id).first()
        elif je.accounting_record_id:
            ar = db.query(AccountingRecord).filter(AccountingRecord.id == je.accounting_record_id).first()
            if ar and ar.document_id:
                doc = db.query(UploadedDocument).filter(UploadedDocument.id == ar.document_id).first()

        if not doc:
            continue

        c_name, c_gst, tmpl = resolve_counterparty_for_doc(doc, client, db)

        needs_update = (
            je.counterparty_name != c_name
            or je.counterparty_gstin != c_gst
            or je.voucher_template != tmpl
        )

        if needs_update:
            changed += 1
            print(f"  Voucher #{je.entry_number} ({je.entry_type} | Ref: {je.reference_number}):")
            print(f"     Old: party='{je.counterparty_name}', gstin='{je.counterparty_gstin}', template='{je.voucher_template}'")
            print(f"     New: party='{c_name}', gstin='{c_gst}', template='{tmpl}'")
            if not dry_run:
                je.counterparty_name = c_name
                je.counterparty_gstin = c_gst
                je.voucher_template = tmpl

    if not dry_run and changed > 0:
        db.commit()
        print(f"Successfully committed updates for {changed} vouchers.")
    elif dry_run:
        print(f"[DRY-RUN] {changed} vouchers would be updated. Run with --apply to commit.")
    else:
        print(f"All vouchers already up to date (0 changes).")

    return changed


def main():
    parser = argparse.ArgumentParser(description="Backfill voucher counterparties & templates")
    parser.add_argument("--client-id", type=str, help="Client UUID to apply changes to")
    parser.add_argument("--client-code", type=str, help="Client code (e.g. C-1071)")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run only (default)")
    parser.add_argument("--all-clients", action="store_true", help="Run across all clients")

    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        if args.all_clients:
            if not dry_run:
                print("ERROR: --all-clients is only permitted with --dry-run for multi-client safety.")
                sys.exit(1)
            clients = db.query(Client).all()
            total_affected = 0
            for c in clients:
                total_affected += backfill_client(db, c, dry_run=True)
            print(f"\n[SUMMARY] Total vouchers requiring backfill across all clients: {total_affected}")
        elif args.client_id or args.client_code:
            q = db.query(Client)
            if args.client_id:
                q = q.filter(Client.id == uuid.UUID(args.client_id))
            else:
                q = q.filter(Client.client_code == args.client_code)
            client = q.first()
            if not client:
                print(f"Client not found!")
                sys.exit(1)
            backfill_client(db, client, dry_run=dry_run)
        else:
            print("Please specify --client-id <UUID> or --client-code <CODE> or --all-clients --dry-run.")
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
