import json
import os
import sys
import uuid
from decimal import Decimal
from datetime import date

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.models.user import User
from app.models.gst_record import GSTRecord
from app.models.journal_entry import JournalEntry
from app.models.uploaded_document import UploadedDocument
from app.services.gst_filing_service import (
    get_filing_profile,
    get_filing_options,
    get_filing_preview,
)
from app.services.gst_reconciliation_service import GstReconciliationService


def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date,)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Type {type(obj)} not serializable")


def generate_evidence():
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.client_code == "C-1071").first()
        if not client:
            print("ERROR: C-1071 not found!")
            return

        user = db.query(User).filter(User.id == client.user_id).first()
        if not user:
            user = db.query(User).filter(User.role == "admin").first()
        if not user:
            user = db.query(User).first()
        profile = get_filing_profile(client)
        today = date(2026, 10, 9)

        # 1. Filing Options
        options = get_filing_options(db, client, today=today)

        # 2. Filing Previews
        preview_3b = get_filing_preview(
            db, client, period="2026-Q2", form="GSTR-3B", user=user, today=today
        )
        preview_gstr1 = get_filing_preview(
            db, client, period="2026-Q2", form="GSTR-1", user=user, today=today
        )

        # 3. Discrepancies
        discrepancies_resp = GstReconciliationService.detect_discrepancies(
            db=db, client_id=client.id, user=user, period="2026-Q2"
        )
        discrepancies = discrepancies_resp.discrepancies or []
        high_discrepancies = [d for d in discrepancies if getattr(d, "severity", None) in ("HIGH", "CRITICAL")]
        duplicate_discrepancies = [d for d in discrepancies if getattr(d, "rule_code", None) == "DUPLICATE_REJECTED"]

        # 4. GST Summaries
        gstr1_summary = GstReconciliationService.reconcile_gstr1(
            db=db, client_id=client.id, user=user, period="2026-Q2"
        )
        gstr3b_summary = GstReconciliationService.generate_gstr3b(
            db=db, client_id=client.id, user=user, period="2026-Q2"
        )

        # 5. Filed records
        filed_records = (
            db.query(GSTRecord)
            .filter(GSTRecord.client_id == client.id)
            .all()
        )
        active_filed = [r for r in filed_records if getattr(r, "status", None) != "voided"]

        # 6. Journal Entries and Uploaded Documents (E1, EWB1, PDN1)
        jes = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id)
            .all()
        )
        je_map = {}
        for je in jes:
            je_dict = {
                "id": str(je.id),
                "entry_number": je.entry_number,
                "entry_date": je.entry_date.isoformat() if je.entry_date else None,
                "counterparty_name": je.counterparty_name,
                "counterparty_gstin": je.counterparty_gstin,
                "is_reversed": je.is_reversed,
                "lines": [
                    {
                        "line_number": l.line_number,
                        "account_code": l.account.account_code if l.account else None,
                        "account_name": l.account.account_name if l.account else None,
                        "debit": str(l.debit_amount),
                        "credit": str(l.credit_amount),
                        "party_name": l.party_name,
                        "party_gstin": l.party_gstin,
                    }
                    for l in je.lines
                ],
            }
            je_map[je.entry_number] = je_dict

        docs = (
            db.query(UploadedDocument)
            .filter(UploadedDocument.client_id == client.id)
            .all()
        )
        doc_map = {}
        for d in docs:
            doc_map[d.invoice_number or d.file_name or str(d.id)] = {
                "id": str(d.id),
                "invoice_number": d.invoice_number,
                "document_category": d.document_category,
                "status": d.status,
                "rejection_reason": d.rejection_reason,
            }

        evidence = {
            "client": {
                "id": str(client.id),
                "name": client.company_name,
                "client_code": client.client_code,
                "gst_number": client.gst_number,
                "state": client.state,
                "return_frequency_raw": client.return_frequency,
                "profile": profile,
            },
            "filing_options": options,
            "preview_2026_Q2_GSTR_3B": preview_3b,
            "preview_2026_Q2_GSTR_1": preview_gstr1,
            "discrepancies_audit": {
                "total_discrepancies": len(discrepancies),
                "high_severity_count": len(high_discrepancies),
                "duplicate_rejected_alerts": [
                    {
                        "rule_code": d.rule_code,
                        "severity": d.severity,
                        "title": d.title,
                        "description": d.description,
                    }
                    for d in duplicate_discrepancies
                ],
            },
            "gstr1_live_summary": gstr1_summary,
            "gstr3b_live_summary": gstr3b_summary,
            "filed_records_audit": {
                "total_records": len(filed_records),
                "active_non_voided": len(active_filed),
            },
            "journal_entries_sample": list(je_map.values())[:5],
            "documents_sample": list(doc_map.keys()),
        }

        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "evidence_round5"))
        os.makedirs(output_dir, exist_ok=True)
        evidence_file = os.path.join(output_dir, "c1071_live_evidence.json")

        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(evidence, f, default=decimal_serializer, indent=2)

        print(f"Evidence successfully written to {evidence_file}")

    finally:
        db.close()


if __name__ == "__main__":
    generate_evidence()
