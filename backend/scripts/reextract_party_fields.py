"""
Party Field Sanitization & OCR Re-extraction Script (D6)
=========================================================
Identifies and fixes party field corruptions on uploaded documents:
1. Cleans "(From)" artifact on B2C/cash memos (e.g. S3).
2. Cleans "Entered Date" artifact on e-way bills and extracts genuine From/To parties and recipient GSTIN.
3. Extracts genuine customer and recipient GSTIN from the Recipient (Bill To / Ship To) block on e-invoices.
4. Updates document columns (customer, vendor, gstin) and structured metadata_ fields.

Multi-Client Safe:
- Does not hardcode client ID, GSTIN, or company name.
- Dynamically resolves client details and parses source PDF text / metadata.

Usage:
    python backend/scripts/reextract_party_fields.py --dry-run --client-id <CLIENT_UUID>
    python backend/scripts/reextract_party_fields.py --apply --client-id <CLIENT_UUID>
    python backend/scripts/reextract_party_fields.py --apply --all-clients
"""

import sys
import os
import re
import json
import argparse
import uuid
from typing import List, Dict, Any, Optional, Tuple

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.uploaded_document import UploadedDocument
from app.models.client import Client


def extract_pdf_text(file_path: str) -> str:
    """Extract full raw text from a PDF file using pypdf or PyMuPDF."""
    if not os.path.exists(file_path):
        return ""
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
    except Exception:
        pass

    try:
        import fitz
        doc = fitz.open(file_path)
        text = "\n".join(page.get_text() or "" for page in doc)
        doc.close()
        return text
    except Exception:
        return ""


def sanitize_document_parties(
    doc: UploadedDocument,
    client: Client,
    backend_dir: str,
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Sanitize and re-extract party fields for a single document.
    Returns (changed: bool, updates: dict, change_reasons: list[str]).
    """
    changed = False
    updates: Dict[str, Any] = {}
    reasons: List[str] = []

    # Resolve PDF on disk
    raw_text = ""
    if doc.file_path:
        full_path = os.path.join(backend_dir, doc.file_path.replace("\\", "/"))
        if os.path.exists(full_path):
            raw_text = extract_pdf_text(full_path)

    # Load existing metadata fields
    meta_dict: Dict[str, Any] = {}
    if doc.metadata_:
        try:
            meta_dict = json.loads(doc.metadata_)
            if not isinstance(meta_dict, dict):
                meta_dict = {}
        except Exception:
            meta_dict = {}
    fields = meta_dict.get("fields")
    if not isinstance(fields, dict):
        fields = {}
        meta_dict["fields"] = fields

    def _get_f(k: str) -> str:
        v = fields.get(k)
        if isinstance(v, dict):
            return str(v.get("value") or "").strip()
        return str(v or "").strip()

    def _set_f(k: str, val: Any):
        fields[k] = {"value": val, "confidence": "extracted"}

    cur_vendor = (doc.vendor or "").strip()
    cur_customer = (doc.customer or "").strip()
    cur_gstin = (doc.gstin or "").strip()

    # ── Rule 1: Clean "(From)" artifact on S3 / invoices ───────────────────
    if cur_vendor == "(From)" or cur_vendor.lower() in ("(from)", "from", "supplier (from)"):
        # Check if PDF text has Supplier (From)\n<Company>
        m_sup = re.search(r"Supplier\s*(?:\(From\))?[:\s]*\n([^\n]+)", raw_text, re.I)
        new_v = m_sup.group(1).strip() if m_sup else client.company_name
        updates["vendor"] = new_v
        reasons.append(f"Cleaned vendor '(From)' -> '{new_v}'")
        changed = True

    if "(From)" in cur_vendor and cur_vendor != "(From)":
        new_v = re.sub(r"\s*\(From\)\s*", "", cur_vendor, flags=re.I).strip()
        updates["vendor"] = new_v
        reasons.append(f"Stripped '(From)' from vendor -> '{new_v}'")
        changed = True

    if "(From)" in cur_customer:
        new_c = re.sub(r"\s*\(From\)\s*", "", cur_customer, flags=re.I).strip()
        updates["customer"] = new_c
        reasons.append(f"Stripped '(From)' from customer -> '{new_c}'")
        changed = True

    # ── Rule 2: Clean "Entered Date" on e-way bills ───────────────────────
    is_ewb = doc.document_category == "e_way_bill" or "e-way" in (doc.file_name or "").lower()
    if is_ewb or cur_vendor == "Entered Date" or "entered date" in cur_vendor.lower():
        from_party = ""
        to_party = ""
        to_gstin = ""

        if raw_text:
            m_from = re.search(r"From\s*(?:\(Dispatch\))?[:\s]*\n([A-Za-z0-9 &.,()-]{3,60}?)(?:\n|GSTIN)", raw_text, re.I)
            if m_from:
                from_party = m_from.group(1).strip()
            m_to = re.search(r"To\s*(?:\(Ship\))?[:\s]*\n([A-Za-z0-9 &.,()-]{3,60}?)(?:\n|GSTIN)", raw_text, re.I)
            if m_to:
                to_party = m_to.group(1).strip()
            # Find GSTIN under To (Ship) block
            to_block = re.search(r"To\s*(?:\(Ship\))?[:\s]*\n.*?(?:PART|PART - B|$)", raw_text, re.DOTALL | re.I)
            if to_block:
                m_tgst = re.search(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", to_block.group(0))
                if m_tgst:
                    to_gstin = m_tgst.group(1).strip().upper()

        if not from_party and cur_vendor in ("Entered Date", "(From)", ""):
            from_party = client.company_name

        if from_party and from_party != cur_vendor:
            updates["vendor"] = from_party
            reasons.append(f"E-Way Bill: corrected vendor '{cur_vendor}' -> '{from_party}'")
            changed = True

        if to_party and to_party != cur_customer:
            updates["customer"] = to_party
            reasons.append(f"E-Way Bill: extracted customer -> '{to_party}'")
            changed = True

        if to_gstin:
            _set_f("customer_gstin", to_gstin)
            _set_f("recipient_gstin", to_gstin)
            reasons.append(f"E-Way Bill: extracted customer GSTIN -> '{to_gstin}'")
            changed = True

    # ── Rule 3: Extract Customer from Recipient Block on e-Invoices ──────
    is_einv = doc.document_category == "e_invoice" or "e-invoice" in (doc.file_name or "").lower()
    if is_einv:
        recipient_name = ""
        recipient_gstin = ""
        pos_code = ""
        pos_state = ""

        if raw_text:
            m_rec = re.search(r"Recipient\s*(?:\(Bill To\s*/\s*Ship To\))?[:\s]*\n([A-Za-z0-9 &.,()-]{3,60}?)(?:\n|GSTIN)", raw_text, re.I)
            if m_rec:
                recipient_name = m_rec.group(1).strip()
            # Recipient GSTIN
            rec_block = re.search(r"Recipient\s*(?:\(Bill To\s*/\s*Ship To\))?[:\s]*\n.*?(?:Document No|#|HSN|$)", raw_text, re.DOTALL | re.I)
            if rec_block:
                m_rgst = re.search(r"GSTIN:\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])", rec_block.group(0), re.I)
                if m_rgst:
                    recipient_gstin = m_rgst.group(1).strip().upper()
                m_pos = re.search(r"Place of Supply:\s*([A-Za-z0-9 ()-]+)", rec_block.group(0), re.I)
                if m_pos:
                    pos_state = m_pos.group(1).strip()
                    m_code = re.search(r"\b([0-9]{2})\b", pos_state)
                    if m_code:
                        pos_code = m_code.group(1)

        # Fallback to metadata if already present in OCR metadata
        if not recipient_name:
            recipient_name = _get_f("buyer_name") or _get_f("recipient_name") or _get_f("customer")
        if not recipient_gstin:
            recipient_gstin = _get_f("customer_gstin") or _get_f("recipient_gstin") or _get_f("buyer_gstin")

        if recipient_name and recipient_name != cur_customer:
            updates["customer"] = recipient_name
            reasons.append(f"e-Invoice: extracted customer from Recipient block -> '{recipient_name}'")
            changed = True

        if recipient_gstin:
            _set_f("customer_gstin", recipient_gstin)
            _set_f("recipient_gstin", recipient_gstin)
            _set_f("buyer_gstin", recipient_gstin)
            reasons.append(f"e-Invoice: extracted recipient GSTIN -> '{recipient_gstin}'")
            changed = True

        if client.gst_number:
            _set_f("supplier_gstin", client.gst_number)

        if pos_code:
            _set_f("place_of_supply_code", pos_code)
        if pos_state:
            _set_f("place_of_supply", pos_state)

        # Taxable amount and IGST
        if doc.taxable_amount:
            _set_f("taxable_amount", float(doc.taxable_amount))
        if doc.igst:
            _set_f("igst_amount", float(doc.igst))

    # If metadata fields were updated, save serialized JSON
    if changed:
        updates["metadata_"] = json.dumps(meta_dict)

    return changed, updates, reasons


def run_party_sanitization(
    client_id: Optional[uuid.UUID] = None,
    dry_run: bool = True,
) -> int:
    """Run party field sanitization across documents."""
    db: Session = SessionLocal()
    try:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        client_query = db.query(Client)
        if client_id:
            client_query = client_query.filter(Client.id == client_id)
        clients = client_query.all()

        if not clients:
            print(f"[ERROR] No client found matching ID: {client_id}")
            return 1

        total_docs_processed = 0
        total_docs_updated = 0

        mode_str = "[DRY-RUN]" if dry_run else "[APPLY]"
        print(f"\n{mode_str} Starting Party Field Sanitization & OCR Re-extraction")
        print("=" * 80)

        for client in clients:
            print(f"\nProcessing Client: {client.company_name} ({client.client_code}, GSTIN: {client.gst_number})")
            docs = db.query(UploadedDocument).filter(
                UploadedDocument.client_id == client.id,
                UploadedDocument.status != "rejected",
            ).order_by(UploadedDocument.created_at.asc()).all()

            for doc in docs:
                total_docs_processed += 1
                changed, updates, reasons = sanitize_document_parties(doc, client, backend_dir)

                if changed:
                    total_docs_updated += 1
                    print(f"  • Doc #{doc.invoice_number or doc.id} [{doc.document_category}]:")
                    for r in reasons:
                        print(f"      - {r}")

                    if not dry_run:
                        for k, v in updates.items():
                            setattr(doc, k, v)
                        db.flush()

        if not dry_run:
            db.commit()
            print(f"\n[APPLY] Successfully updated {total_docs_updated} of {total_docs_processed} documents in DB.")
        else:
            print(f"\n[DRY-RUN] Found {total_docs_updated} of {total_docs_processed} documents requiring party sanitization.")
            print("Run with --apply to commit these changes to the database.")

        print("=" * 80)
        return 0
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Sanitize party fields and re-extract e-invoice recipient blocks (D6)")
    parser.add_argument("--client-id", type=str, default=None, help="Client UUID to sanitize")
    parser.add_argument("--all-clients", action="store_true", help="Sanitize documents across all clients")
    parser.add_argument("--apply", action="store_true", help="Commit changes to database (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview changes without modifying DB")

    args = parser.parse_args()

    dry_run = not args.apply

    if not args.client_id and not args.all_clients:
        print("[ERROR] You must specify either --client-id <UUID> or --all-clients (Multi-Client Safety Rule R10).")
        sys.exit(1)

    c_id = None
    if args.client_id:
        try:
            c_id = uuid.UUID(args.client_id)
        except ValueError:
            print(f"[ERROR] Invalid UUID format: {args.client_id}")
            sys.exit(1)

    exit_code = run_party_sanitization(client_id=c_id, dry_run=dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
