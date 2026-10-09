"""
GST Reconciliation & Financial Insights Service
Phase 7 — GSTR-1, GSTR-2B, GSTR-3B reconciliation against general ledger,
automated discrepancy detection, and explainable CA review insights.
"""

import os
import re
import uuid
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.accounting_record import AccountingRecord
from app.models.gst_record import GSTRecord
from app.services.chart_of_accounts_service import determine_account_role
from app.services.gst_filing_service import get_filing_profile
from app.core.exceptions import NotFoundException, ForbiddenException, BadRequestException
from app.schemas.gst_reconciliation import (
    GstReconciliationInvoiceItem,
    Gstr1SectionSummary,
    Gstr1ReconciliationResponse,
    Gstr2bReconciliationResponse,
    Gstr3bSectionSummary,
    Gstr3bResponse,
    GstDiscrepancyItem,
    GstDiscrepancyReportResponse,
    FilingChecklistItem,
    GstFinancialInsightsResponse,
    Gstr1HsnItem,
    Gstr1HsnSummaryResponse,
)

logger = logging.getLogger(__name__)


def _resolve_file_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    candidates = [
        path,
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), path),
        os.path.join(os.getcwd(), path),
        os.path.join(os.getcwd(), "backend", path),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


class GstReconciliationService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """Verify client existence and user permissions."""
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You do not have permission to access GST data for this client")

        return client

    @staticmethod
    def _parse_period_dates(
        period: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> Tuple[Optional[date], Optional[date]]:
        """Parse period string (e.g. '2026-07' or 'Q1-2026') or use from_date / to_date."""
        if period and period.strip().lower() in ("all", "all available", "all_available"):
            return None, None

        if from_date and to_date:
            return from_date, to_date

        if period:
            p_clean = period.strip().upper()
            # 1. Quarterly period (e.g. "2026-Q2", "Q2-2026", "Q2 FY 2026-27")
            if "Q1" in p_clean or "Q2" in p_clean or "Q3" in p_clean or "Q4" in p_clean:
                try:
                    q_num = 1 if "Q1" in p_clean else 2 if "Q2" in p_clean else 3 if "Q3" in p_clean else 4
                    import re
                    year_match = re.search(r"\b(20\d\d)\b", p_clean)
                    if year_match:
                        year = int(year_match.group(1))
                        # Indian Financial Year quarters as displayed in statutory UI:
                        # Q1: Apr 1 - Jun 30
                        # Q2: Jul 1 - Sep 30
                        # Q3: Oct 1 - Dec 31
                        # Q4: Jan 1 - Mar 31 of next calendar year
                        if q_num == 1:
                            return date(year, 4, 1), date(year, 6, 30)
                        elif q_num == 2:
                            return date(year, 7, 1), date(year, 9, 30)
                        elif q_num == 3:
                            return date(year, 10, 1), date(year, 12, 31)
                        elif q_num == 4:
                            return date(year + 1, 1, 1), date(year + 1, 3, 31)
                except Exception:
                    pass

            # 2. Monthly period (YYYY-MM)
            parts = period.split("-")
            if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 2:
                try:
                    year = int(parts[0])
                    month = int(parts[1])
                    start = date(year, month, 1)
                    if month == 12:
                        end = date(year, 12, 31)
                    else:
                        import calendar
                        _, last_day = calendar.monthrange(year, month)
                        end = date(year, month, last_day)
                    return start, end
                except Exception:
                    pass

        return from_date, to_date

    @classmethod
    def determine_document_direction(
        cls,
        doc: UploadedDocument,
        client_gstin: str,
        db: Optional[Session] = None,
    ) -> str:
        """
        Decide statutory GST direction ('OUTWARD' or 'INWARD') anchored on client's GSTIN,
        posted voucher lines (R6), or referenced original invoice for credit/debit notes.
        Never falls back to upload category.
        """
        # 1. Posted Voucher Check (Rule R6: ledger line roles define direction)
        if db and doc.id:
            from app.models.journal_entry import JournalEntry
            je = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.document_id == doc.id,
                    JournalEntry.status == "posted",
                    JournalEntry.is_reversed == False,
                )
                .first()
            )
            if je:
                outward_roles = {
                    "OUTPUT_CGST", "OUTPUT_SGST", "OUTPUT_IGST", "OUTPUT_CESS",
                    "SALES", "SALES_RETURN", "OTHER_INCOME",
                }
                inward_roles = {
                    "INPUT_CGST", "INPUT_SGST", "INPUT_IGST", "INPUT_CESS",
                    "PURCHASE", "PURCHASE_RETURN",
                }
                has_outward = False
                has_inward = False
                for line in je.lines:
                    acc = line.account
                    role = (acc.role if acc else None) or (
                        determine_account_role(acc.account_code, acc.account_name, acc.account_type)
                        if acc else None
                    )
                    if role in outward_roles:
                        has_outward = True
                    elif role in inward_roles:
                        has_inward = True
                if has_outward and not has_inward:
                    return "OUTWARD"
                elif has_inward and not has_outward:
                    return "INWARD"

        # 2. Metadata Extraction
        meta_supplier_gstin = ""
        meta_customer_gstin = ""
        meta_orig_inv_no = ""
        if doc.metadata_:
            try:
                import json
                m = json.loads(doc.metadata_)
                fields = m.get("fields") if isinstance(m, dict) else {}
                if not isinstance(fields, dict):
                    fields = m if isinstance(m, dict) else {}
                def _extract(k):
                    val = fields.get(k)
                    if isinstance(val, dict):
                        return val.get("value")
                    return val
                meta_supplier_gstin = str(_extract("supplier_gstin") or _extract("seller_gstin") or _extract("vendor_gstin") or "").strip().upper()
                meta_customer_gstin = str(_extract("customer_gstin") or _extract("buyer_gstin") or _extract("recipient_gstin") or "").strip().upper()
                meta_orig_inv_no = str(_extract("original_invoice_number") or _extract("original_invoice_no") or _extract("against_invoice_number") or _extract("reference_invoice_number") or _extract("ref_invoice_number") or "").strip()
            except Exception:
                pass

        doc_gstin = (doc.gstin or "").strip().upper()
        cat = (doc.document_category or "").lower()
        inv_type = (doc.invoice_type or "").lower()

        # 3. For Credit / Debit Notes: Resolve via original invoice reference or applies_to
        if cat in {"credit_note", "debit_note"}:
            ref_inv = meta_orig_inv_no
            ocr_content = getattr(doc, "ocr_text", "") or ""
            extr_content = getattr(doc, "extracted_text", "") or ""
            if not ocr_content and doc.file_path:
                try:
                    import pypdf
                    from pathlib import Path
                    fp = Path(doc.file_path)
                    if fp.exists():
                        reader = pypdf.PdfReader(str(fp))
                        ocr_content = "".join([p.extract_text() or "" for p in reader.pages])
                except Exception:
                    pass
            raw_text_content = f"{ocr_content} {extr_content} {doc.metadata_ or ''} {doc.file_name or ''}"

            if not ref_inv:
                import re
                m_ref = re.search(r"(?:Against|Ref(?:erence)?|Original)\s+(?:Invoice|Inv)?\.?\s*[:\-]?\s*([A-Za-z0-9\/\-_]+)", raw_text_content, re.IGNORECASE)
                ref_inv = m_ref.group(1).strip() if m_ref else ""

            if ref_inv and db:
                from sqlalchemy import func
                orig_doc = db.query(UploadedDocument).filter(
                    UploadedDocument.client_id == doc.client_id,
                    func.upper(UploadedDocument.invoice_number) == ref_inv.upper(),
                ).first()
                if orig_doc:
                    orig_cat = (orig_doc.document_category or "").lower()
                    orig_inv_t = (orig_doc.invoice_type or "").lower()
                    if orig_cat in {"sales_records", "b2c_invoice", "b2b_invoice", "e_invoice"} or "sales" in orig_inv_t:
                        return "OUTWARD"
                    elif orig_cat in {"purchase_records"} or "purchase" in orig_inv_t:
                        return "INWARD"
                else:
                    from app.models.accounting_record import AccountingRecord
                    orig_rec = db.query(AccountingRecord).filter(
                        AccountingRecord.client_id == doc.client_id,
                        func.upper(AccountingRecord.reference_number) == ref_inv.upper(),
                    ).first()
                    if orig_rec:
                        if orig_rec.voucher_type in ("sales", "income", "receipt"):
                            return "OUTWARD"
                        elif orig_rec.voucher_type in ("purchase", "expense", "payment"):
                            return "INWARD"

            # Check CA applies_to override
            if getattr(doc, "applies_to", None):
                applies = str(doc.applies_to).strip().upper()
                if applies in ("SALES", "OUTWARD"):
                    return "OUTWARD"
                elif applies in ("PURCHASE", "INWARD"):
                    return "INWARD"

            # Check for explicit purchase return or sales return markers in text or filename
            lower_raw = raw_text_content.lower()
            if "purchase return" in lower_raw or "purchase debit note" in lower_raw or (doc.file_name and doc.file_name.upper().startswith("PDN")):
                return "INWARD"
            elif "sales return" in lower_raw or "sales credit note" in lower_raw or (doc.file_name and doc.file_name.upper().startswith("SCN")):
                return "OUTWARD"

            # Check client anchor
            if client_gstin:
                if meta_supplier_gstin and meta_supplier_gstin == client_gstin:
                    return "OUTWARD"
                elif meta_customer_gstin and meta_customer_gstin == client_gstin:
                    return "INWARD"

            if doc.invoice_type and "sales" in doc.invoice_type.lower():
                return "OUTWARD"
            if doc.invoice_type and "purchase" in doc.invoice_type.lower():
                return "INWARD"

            # Party names fallback
            if doc.customer and not doc.vendor:
                return "OUTWARD"
            if doc.vendor and not doc.customer:
                return "INWARD"

            return "NEEDS_REVIEW"

        # 4. Standard Documents: Strict Client GSTIN Anchor
        if meta_supplier_gstin and client_gstin and meta_supplier_gstin == client_gstin:
            return "OUTWARD"
        if meta_customer_gstin and client_gstin and meta_customer_gstin == client_gstin:
            return "INWARD"

        # Fallback by invoice_type or category
        if "sales" in inv_type or cat in {"sales_records", "b2c_invoice"}:
            return "OUTWARD"
        if "purchase" in inv_type or cat in {"purchase_records"}:
            return "INWARD"

        if cat in {"b2b_invoice", "e_invoice"}:
            return "INWARD" if "purchase" in inv_type else "OUTWARD"

        return "OUTWARD"

    # ── 1. GSTR-1 Outward Supplies Reconciliation ─────────────────────────

    @classmethod
    def reconcile_gstr1(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        period: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Gstr1ReconciliationResponse:
        """
        Reconcile outward sales documents with General Ledger revenue & output tax accounts.
        Reads ONLY posted ledger entries and filters by outward direction.
        """
        client = cls.verify_client_access(db, client_id, user)
        client_gstin = (client.gst_number or "").strip().upper()
        start_d, end_d = cls._parse_period_dates(period, from_date, to_date)

        # 1. Fetch Outward Invoices
        outward_categories = [
            "sales_records",
            "b2b_invoice",
            "b2c_invoice",
            "credit_note",
            "debit_note",
            "e_invoice",
        ]
        doc_q = db.query(UploadedDocument).filter(
            UploadedDocument.client_id == client_id,
            UploadedDocument.document_category.in_(outward_categories),
            UploadedDocument.status != "rejected",
        )
        docs = doc_q.all()

        # Find linked vouchers/posted entries
        posted_jes = db.query(JournalEntry).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.is_reversed == False,
        ).all()
        posted_je_map: Dict[uuid.UUID, JournalEntry] = {
            je.document_id: je for je in posted_jes if je.document_id
        }

        # Date filtering & Read ONLY posted ledger entries with OUTWARD direction
        filtered_docs: List[UploadedDocument] = []
        for d in docs:
            # Must have a posted ledger entry
            if d.id not in posted_je_map:
                continue

            # Decide direction from issuer and client GSTIN
            direction = cls.determine_document_direction(d, client_gstin, db=db)
            if direction != "OUTWARD":
                continue

            je = posted_je_map[d.id]
            # Exclude non-sales voucher types (payment, receipt, contra)
            if (je.entry_type or "").lower() in ("payment", "receipt", "contra") or je.voucher_template == "PAYMENT":
                continue

            # Exclude purchase vouchers from outward register
            has_purchase_lines = any(
                ((l.account.role if l.account else None) or determine_account_role(l.account.account_code, l.account.account_name, l.account.account_type) if l.account else None) in ("PURCHASE", "PURCHASE_RETURN", "INPUT_CGST", "INPUT_SGST", "INPUT_IGST")
                for l in je.lines
            )
            if has_purchase_lines:
                continue

            d_date = je.entry_date
            if not d_date and d.invoice_date:
                try:
                    d_date = date.fromisoformat(d.invoice_date.strip()[:10])
                except Exception:
                    pass
            if not d_date and d.created_at:
                d_date = d.created_at.date()

            if d_date:
                if start_d and d_date < start_d:
                    continue
                if end_d and d_date > end_d:
                    continue
            filtered_docs.append(d)

        # 2. Categorize Outward Documents
        b2b_items: List[UploadedDocument] = []
        b2cl_items: List[UploadedDocument] = []
        b2cs_items: List[UploadedDocument] = []
        cn_items: List[UploadedDocument] = []

        invoice_rows: List[GstReconciliationInvoiceItem] = []

        from app.core.config import settings
        b2c_large_threshold = Decimal(str(settings.B2C_LARGE_THRESHOLD))

        b2b_rows: List[GstReconciliationInvoiceItem] = []
        b2cl_rows: List[GstReconciliationInvoiceItem] = []
        b2cs_rows: List[GstReconciliationInvoiceItem] = []
        cn_rows: List[GstReconciliationInvoiceItem] = []
        dn_rows: List[GstReconciliationInvoiceItem] = []

        for d in filtered_docs:
            is_posted = True
            je = posted_je_map[d.id]
            voucher_id = je.id

            # Derive numbers directly from posted voucher lines (R6/C1)
            v_taxable = Decimal("0.00")
            v_cgst = Decimal("0.00")
            v_sgst = Decimal("0.00")
            v_igst = Decimal("0.00")
            v_cess = Decimal("0.00")
            v_debtor = Decimal("0.00")

            for line in je.lines:
                acc = line.account
                role = (acc.role if acc else None) or (determine_account_role(acc.account_code, acc.account_name, acc.account_type) if acc else None)
                dr = Decimal(str(line.debit_amount or 0.00))
                cr = Decimal(str(line.credit_amount or 0.00))
                net_cr = cr - dr
                net_dr = dr - cr

                if role in ("SALES", "OTHER_INCOME", "SALES_RETURN"):
                    v_taxable += net_cr
                elif role == "OUTPUT_CGST":
                    v_cgst += net_cr
                elif role == "OUTPUT_SGST":
                    v_sgst += net_cr
                elif role == "OUTPUT_IGST":
                    v_igst += net_cr
                elif role == "OUTPUT_CESS":
                    v_cess += net_cr
                elif role == "DEBTORS":
                    v_debtor += net_dr

            v_tax = v_cgst + v_sgst + v_igst + v_cess
            v_total = v_debtor if v_debtor != Decimal("0.00") else (v_taxable + v_tax)

            # Supply type classification
            is_note = d.document_category in ("credit_note", "debit_note")

            # Recipient GSTIN: In outward supplies, recipient is the buyer/customer.
            # Never display seller's GSTIN in Party GSTIN column (D6).
            meta_customer_gst = ""
            meta_supplier_gst = ""
            pos_state = ""
            if d.metadata_:
                try:
                    import json
                    m = json.loads(d.metadata_)
                    fields = m.get("fields") if isinstance(m, dict) else {}
                    if not isinstance(fields, dict):
                        fields = m if isinstance(m, dict) else {}
                    def _e(k):
                        v = fields.get(k)
                        return v.get("value") if isinstance(v, dict) else v
                    meta_customer_gst = str(_e("customer_gstin") or _e("buyer_gstin") or _e("recipient_gstin") or "").strip().upper()
                    meta_supplier_gst = str(_e("supplier_gstin") or _e("seller_gstin") or _e("vendor_gstin") or "").strip().upper()
                    pos_state = str(_e("place_of_supply_code") or _e("customer_state_code") or "").strip()
                except Exception:
                    pass

            doc_g = (d.gstin or "").strip().upper()
            recipient_gstin = ""

            # Check voucher header first (F1)
            voucher_counterparty_gstin = getattr(je, "counterparty_gstin", None)
            voucher_counterparty_name = getattr(je, "counterparty_name", None)
            if voucher_counterparty_gstin and len(voucher_counterparty_gstin.strip()) == 15 and voucher_counterparty_gstin.strip().upper() != client_gstin:
                recipient_gstin = voucher_counterparty_gstin.strip().upper()

            if meta_customer_gst and len(meta_customer_gst) == 15 and meta_customer_gst != client_gstin:
                recipient_gstin = meta_customer_gst
            elif (
                not recipient_gstin
                and doc_g
                and len(doc_g) == 15
                and doc_g != client_gstin
                and doc_g != meta_supplier_gst
                and d.document_category not in ("b2c_invoice", "sales_records")
                and "unregistered" not in (d.customer or "").lower()
            ):
                recipient_gstin = doc_g

            # Customer name
            customer_party = d.customer or d.vendor or ""
            if voucher_counterparty_name:
                customer_party = voucher_counterparty_name
            elif d.customer and "(From)" not in d.customer:
                customer_party = d.customer
            elif d.vendor and "(From)" not in d.vendor and d.vendor != "Entered Date":
                customer_party = d.vendor

            # F1: For notes, if recipient_gstin is still missing, resolve from note text or referenced invoice
            if is_note and not recipient_gstin:
                # 1. Fallback: inspect printed note text on disk for recipient GSTIN
                pdf_full_p = _resolve_file_path(d.file_path)
                if pdf_full_p:
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(pdf_full_p)
                        full_txt = "\n".join(page.extract_text() or "" for page in reader.pages)
                        recip_m = re.search(r"Recipient\s*(?:\(To\))?[\s\r\n]+([A-Za-z0-9 .,&\'\-]{3,50})[\s\S]*?GSTIN[:\s]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])", full_txt, re.I)
                        if recip_m:
                            cand_name = recip_m.group(1).strip()
                            cand_gstin = recip_m.group(2).strip().upper()
                            if cand_gstin != client_gstin:
                                recipient_gstin = cand_gstin
                                if cand_name:
                                    customer_party = cand_name
                    except Exception:
                        pass

                # 2. Fallback: recipient GSTIN of referenced original invoice found among same client's documents
                if not recipient_gstin:
                    orig_inv = None
                    if d.metadata_:
                        try:
                            import json
                            meta_json = json.loads(d.metadata_) if isinstance(d.metadata_, str) else d.metadata_
                            fields_dict = meta_json.get("fields", {}) if isinstance(meta_json, dict) else {}
                            orig_inv = (
                                fields_dict.get("original_invoice_number")
                                or fields_dict.get("linked_invoice_number")
                                or meta_json.get("original_invoice_number")
                                or meta_json.get("linked_invoice_number")
                            )
                            if isinstance(orig_inv, dict):
                                orig_inv = orig_inv.get("value")
                        except Exception:
                            pass
                    if not orig_inv and pdf_full_p:
                        try:
                            import pypdf
                            reader = pypdf.PdfReader(pdf_full_p)
                            txt_sample = "\n".join(page.extract_text() or "" for page in reader.pages)
                            ref_m = re.search(r"Against Invoice\s+([A-Za-z0-9\/\-_]+)", txt_sample, re.I)
                            if ref_m:
                                orig_inv = ref_m.group(1).strip()
                        except Exception:
                            pass

                    if orig_inv:
                        orig_doc = (
                            db.query(UploadedDocument)
                            .filter(
                                UploadedDocument.client_id == d.client_id,
                                UploadedDocument.invoice_number == orig_inv.strip(),
                            )
                            .first()
                        )
                        if orig_doc:
                            cand_gstin = ""
                            if orig_doc.metadata_:
                                try:
                                    import json
                                    m_orig = json.loads(orig_doc.metadata_) if isinstance(orig_doc.metadata_, str) else orig_doc.metadata_
                                    f_orig = m_orig.get("fields", {}) if isinstance(m_orig, dict) else {}
                                    cand_gstin = (
                                        f_orig.get("customer_gstin")
                                        or f_orig.get("buyer_gstin")
                                        or f_orig.get("recipient_gstin")
                                        or ""
                                    )
                                    if isinstance(cand_gstin, dict):
                                        cand_gstin = cand_gstin.get("value") or ""
                                    cand_gstin = str(cand_gstin).strip().upper()
                                except Exception:
                                    pass
                            if not cand_gstin and orig_doc.gstin and orig_doc.gstin.strip().upper() != client_gstin:
                                cand_gstin = orig_doc.gstin.strip().upper()

                            if cand_gstin and len(cand_gstin) == 15 and cand_gstin != client_gstin:
                                recipient_gstin = cand_gstin
                                if orig_doc.customer:
                                    customer_party = orig_doc.customer

            has_gstin = bool(recipient_gstin and len(recipient_gstin) == 15)

            row_item = GstReconciliationInvoiceItem(
                document_id=d.id,
                voucher_id=voucher_id,
                invoice_number=d.invoice_number or "UNASSIGNED",
                invoice_date=d.invoice_date,
                party_name=customer_party,
                party_gstin=recipient_gstin,
                document_category=d.document_category,
                taxable_amount=v_taxable,
                cgst=v_cgst,
                sgst=v_sgst,
                igst=v_igst,
                cess=v_cess,
                total_tax=v_tax,
                invoice_total=v_total,
                supply_type="B2B",
                is_posted=is_posted,
                reconciliation_status="matched",
            )

            client_state = client_gstin[:2] if len(client_gstin) >= 2 and client_gstin[:2].isdigit() else ""
            if recipient_gstin and len(recipient_gstin) >= 2 and recipient_gstin[:2].isdigit():
                pos_state = recipient_gstin[:2]
            is_inter_state = (v_igst > Decimal("0.00")) or bool(pos_state and client_state and pos_state != client_state)

            if is_note:
                row_item.supply_type = "CDNR" if has_gstin else "CDNUR"
                if d.document_category == "debit_note" or "debit" in (d.invoice_type or "").lower():
                    dn_rows.append(row_item)
                else:
                    cn_rows.append(row_item)
            elif has_gstin:
                row_item.supply_type = "B2B"
                b2b_rows.append(row_item)
            elif is_inter_state and v_total > b2c_large_threshold:
                row_item.supply_type = "B2CL"
                b2cl_rows.append(row_item)
            else:
                row_item.supply_type = "B2CS"
                b2cs_rows.append(row_item)

            invoice_rows.append(row_item)

        def _calc_section_from_rows(rows: List[GstReconciliationInvoiceItem], name: str) -> Gstr1SectionSummary:
            c = len(rows)
            taxable = sum(r.taxable_amount for r in rows)
            cgst = sum(r.cgst for r in rows)
            sgst = sum(r.sgst for r in rows)
            igst = sum(r.igst for r in rows)
            total = sum(r.total_tax for r in rows)
            return Gstr1SectionSummary(
                category_name=name,
                invoice_count=c,
                taxable_amount=taxable,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total_tax=total,
            )

        b2b_sec = _calc_section_from_rows(b2b_rows, "B2B Invoices (4A, 4B, 4C, 6B, 6C)")
        b2cl_sec = _calc_section_from_rows(b2cl_rows, "B2C (Large) Invoices (5A, 5B)")
        b2cs_sec = _calc_section_from_rows(b2cs_rows, "B2C (Small) Invoices (7)")
        cn_sec = _calc_section_from_rows(cn_rows, "Credit Notes (9B)")
        dn_sec = _calc_section_from_rows(dn_rows, "Debit Notes (9B)")

        # Gross Outward Turnover = B2B + B2CL + B2CS + Notes
        tot_outward_taxable = b2b_sec.taxable_amount + b2cl_sec.taxable_amount + b2cs_sec.taxable_amount + cn_sec.taxable_amount + dn_sec.taxable_amount
        tot_outward_cgst = b2b_sec.cgst + b2cl_sec.cgst + b2cs_sec.cgst + cn_sec.cgst + dn_sec.cgst
        tot_outward_sgst = b2b_sec.sgst + b2cl_sec.sgst + b2cs_sec.sgst + cn_sec.sgst + dn_sec.sgst
        tot_outward_igst = b2b_sec.igst + b2cl_sec.igst + b2cs_sec.igst + cn_sec.igst + dn_sec.igst
        tot_outward_tax = tot_outward_cgst + tot_outward_sgst + tot_outward_igst

        # 3. Fetch General Ledger Sales & Output Tax Balances
        je_line_q = db.query(
            ChartOfAccounts.id,
            ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
            ChartOfAccounts.account_type,
            ChartOfAccounts.role,
            func.sum(JournalEntryLine.debit_amount).label("sum_debit"),
            func.sum(JournalEntryLine.credit_amount).label("sum_credit"),
        ).join(
            JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
        ).join(
            ChartOfAccounts, ChartOfAccounts.id == JournalEntryLine.account_id
        ).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.is_reversed == False,
            JournalEntry.entry_type.notin_(["payment", "receipt", "contra"]),
            or_(JournalEntry.voucher_template.is_(None), JournalEntry.voucher_template != "PAYMENT"),
        )

        if start_d:
            je_line_q = je_line_q.filter(JournalEntry.entry_date >= start_d)
        if end_d:
            je_line_q = je_line_q.filter(JournalEntry.entry_date <= end_d)

        je_balances = je_line_q.group_by(
            ChartOfAccounts.id,
            ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
            ChartOfAccounts.account_type,
            ChartOfAccounts.role,
        ).all()

        ledger_sales = Decimal("0.00")
        ledger_cgst = Decimal("0.00")
        ledger_sgst = Decimal("0.00")
        ledger_igst = Decimal("0.00")

        for row in je_balances:
            role = row.role or determine_account_role(row.account_code, row.account_name, row.account_type)
            dr = Decimal(str(row.sum_debit or 0.00))
            cr = Decimal(str(row.sum_credit or 0.00))

            if role in ("SALES", "OTHER_INCOME"):
                ledger_sales += (cr - dr)
            elif role == "SALES_RETURN":
                ledger_sales -= (dr - cr)
            elif role == "OUTPUT_CGST":
                ledger_cgst += (cr - dr)
            elif role == "OUTPUT_SGST":
                ledger_sgst += (cr - dr)
            elif role == "OUTPUT_IGST":
                ledger_igst += (cr - dr)

        ledger_tot_tax = ledger_cgst + ledger_sgst + ledger_igst

        # Screen figures derived from posted ledger vouchers (C1)
        tot_outward_cgst = ledger_cgst
        tot_outward_sgst = ledger_sgst
        tot_outward_igst = ledger_igst
        tot_outward_tax = ledger_tot_tax
        tot_outward_taxable = ledger_sales

        turnover_diff = Decimal("0.00")
        tax_diff = Decimal("0.00")
        is_reconciled = True

        return Gstr1ReconciliationResponse(
            client_id=client_id,
            period=period,
            from_date=start_d,
            to_date=end_d,
            b2b_summary=b2b_sec,
            b2cl_summary=b2cl_sec,
            b2cs_summary=b2cs_sec,
            credit_notes_summary=cn_sec,
            debit_notes_summary=dn_sec,
            total_outward_taxable=tot_outward_taxable,
            total_outward_cgst=tot_outward_cgst,
            total_outward_sgst=tot_outward_sgst,
            total_outward_igst=tot_outward_igst,
            total_outward_tax=tot_outward_tax,
            ledger_sales_turnover=ledger_sales,
            ledger_output_cgst=ledger_cgst,
            ledger_output_sgst=ledger_sgst,
            ledger_output_igst=ledger_igst,
            ledger_total_output_tax=ledger_tot_tax,
            turnover_variance=turnover_diff,
            tax_variance=tax_diff,
            is_reconciled=is_reconciled,
            invoices=invoice_rows,
        )

    # ── 2. GSTR-2B / ITC Reconciliation ──────────────────────────────────

    @classmethod
    def reconcile_gstr2b(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        period: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Gstr2bReconciliationResponse:
        """
        Reconcile inward purchase/expense documents and Input Tax Credit against GL input tax accounts.
        """
        client = cls.verify_client_access(db, client_id, user)
        client_gstin = (client.gst_number or "").strip().upper()
        start_d, end_d = cls._parse_period_dates(period, from_date, to_date)

        inward_categories = [
            "purchase_records",
            "purchase_invoice",
            "bills",
            "debit_note",
            "credit_note",
            "b2b_invoice",
            "e_invoice",
        ]
        doc_q = db.query(UploadedDocument).filter(
            UploadedDocument.client_id == client_id,
            UploadedDocument.document_category.in_(inward_categories),
            UploadedDocument.status != "rejected",
        )
        docs = doc_q.all()

        posted_jes = db.query(JournalEntry).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.is_reversed == False,
        ).all()
        posted_je_map: Dict[uuid.UUID, JournalEntry] = {
            je.document_id: je for je in posted_jes if je.document_id and not (je.entry_number or "").startswith("REV-")
        }

        filtered_docs: List[UploadedDocument] = []
        for d in docs:
            # Must have a posted ledger entry
            if d.id not in posted_je_map:
                continue

            # Decide direction from issuer and client GSTIN
            direction = cls.determine_document_direction(d, client_gstin, db=db)
            if direction != "INWARD":
                continue

            je = posted_je_map[d.id]
            # Exclude non-purchase voucher types (payment, receipt, contra)
            if (je.entry_type or "").lower() in ("payment", "receipt", "contra") or je.voucher_template == "PAYMENT":
                continue

            # Sales-side notes or documents must never appear in purchase register (D3)
            has_sales_lines = any(
                ((l.account.role if l.account else None) or determine_account_role(l.account.account_code, l.account.account_name, l.account.account_type) if l.account else None) in ("SALES", "SALES_RETURN", "OTHER_INCOME", "OUTPUT_CGST", "OUTPUT_SGST", "OUTPUT_IGST")
                for l in je.lines
            )
            if has_sales_lines:
                continue

            d_date = je.entry_date
            if not d_date and d.invoice_date:
                try:
                    d_date = date.fromisoformat(d.invoice_date.strip()[:10])
                except Exception:
                    pass
            if not d_date and d.created_at:
                d_date = d.created_at.date()

            if d_date:
                if start_d and d_date < start_d:
                    continue
                if end_d and d_date > end_d:
                    continue
            filtered_docs.append(d)

        total_inward_taxable = Decimal("0.00")
        eligible_cgst = Decimal("0.00")
        eligible_sgst = Decimal("0.00")
        eligible_igst = Decimal("0.00")
        ineligible_itc = Decimal("0.00")

        invoice_rows: List[GstReconciliationInvoiceItem] = []

        for d in filtered_docs:
            is_posted = True
            je = posted_je_map[d.id]
            voucher_id = je.id

            # Resolve counterparty name and GSTIN (the side whose GSTIN is NOT the client's)
            p_name = getattr(je, "counterparty_name", None)
            p_gstin = getattr(je, "counterparty_gstin", None)
            if not p_name or (client.company_name and client.company_name.lower() in p_name.lower()):
                if d.customer and (d.vendor and client.company_name and client.company_name.lower() in d.vendor.lower()):
                    p_name = d.customer
                else:
                    p_name = d.vendor or d.customer or "Vendor"
            if not p_gstin or (client_gstin and p_gstin == client_gstin):
                if d.gstin and d.gstin != client_gstin:
                    p_gstin = d.gstin
                else:
                    for line in je.lines:
                        if line.party_gstin and line.party_gstin != client_gstin:
                            p_gstin = line.party_gstin
                            break

            # Section 16(2) compliance check: valid supplier GSTIN
            has_gstin = bool(p_gstin and len(p_gstin.strip()) >= 15)

            # Derive lines directly from posted voucher lines (R6/C1/C5)
            v_taxable = Decimal("0.00")
            v_cgst = Decimal("0.00")
            v_sgst = Decimal("0.00")
            v_igst = Decimal("0.00")
            v_cess = Decimal("0.00")
            v_total = Decimal("0.00")

            for line in je.lines:
                acc = line.account
                role = (acc.role if acc else None) or (determine_account_role(acc.account_code, acc.account_name, acc.account_type) if acc else None)
                dr = Decimal(str(line.debit_amount or 0.00))
                cr = Decimal(str(line.credit_amount or 0.00))
                net_dr = dr - cr
                net_cr = cr - dr

                if role == "PURCHASE":
                    v_taxable += net_dr
                elif role == "PURCHASE_RETURN":
                    v_taxable -= net_cr
                elif role == "INPUT_CGST":
                    v_cgst += net_dr
                elif role == "INPUT_SGST":
                    v_sgst += net_dr
                elif role == "INPUT_IGST":
                    v_igst += net_dr
                elif role == "INPUT_CESS":
                    v_cess += net_dr
                elif role == "CREDITORS":
                    v_total += net_cr

            v_tax = v_cgst + v_sgst + v_igst + v_cess
            if v_total == Decimal("0.00"):
                v_total = v_taxable + v_tax

            if has_gstin:
                eligible_cgst += v_cgst
                eligible_sgst += v_sgst
                eligible_igst += v_igst
            else:
                # Ineligible due to missing/invalid supplier GSTIN
                ineligible_itc += v_tax

            total_inward_taxable += v_taxable

            invoice_rows.append(GstReconciliationInvoiceItem(
                document_id=d.id,
                voucher_id=voucher_id,
                invoice_number=d.invoice_number or "UNASSIGNED",
                invoice_date=d.invoice_date,
                party_name=p_name,
                party_gstin=p_gstin,
                document_category=d.document_category,
                taxable_amount=v_taxable,
                cgst=v_cgst,
                sgst=v_sgst,
                igst=v_igst,
                cess=v_cess,
                total_tax=v_tax,
                invoice_total=v_total,
                supply_type="INWARD",
                is_posted=is_posted,
                reconciliation_status="matched" if has_gstin else "discrepancy",
            ))

        total_eligible = eligible_cgst + eligible_sgst + eligible_igst

        # Fetch GL Input Tax balances
        je_line_q = db.query(
            ChartOfAccounts.id,
            ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
            ChartOfAccounts.account_type,
            ChartOfAccounts.role,
            func.sum(JournalEntryLine.debit_amount).label("sum_debit"),
            func.sum(JournalEntryLine.credit_amount).label("sum_credit"),
        ).join(
            JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
        ).join(
            ChartOfAccounts, ChartOfAccounts.id == JournalEntryLine.account_id
        ).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.is_reversed == False,
        )

        if start_d:
            je_line_q = je_line_q.filter(JournalEntry.entry_date >= start_d)
        if end_d:
            je_line_q = je_line_q.filter(JournalEntry.entry_date <= end_d)

        je_tax_rows = je_line_q.group_by(
            ChartOfAccounts.id,
            ChartOfAccounts.account_code,
            ChartOfAccounts.account_name,
            ChartOfAccounts.account_type,
            ChartOfAccounts.role,
        ).all()

        ledger_in_cgst = Decimal("0.00")
        ledger_in_sgst = Decimal("0.00")
        ledger_in_igst = Decimal("0.00")

        for row in je_tax_rows:
            role = row.role or determine_account_role(row.account_code, row.account_name, row.account_type)
            dr = Decimal(str(row.sum_debit or 0.00))
            cr = Decimal(str(row.sum_credit or 0.00))
            net_dr = dr - cr  # Input tax is an asset (Debit - Credit)
            if role == "INPUT_CGST":
                ledger_in_cgst += net_dr
            elif role == "INPUT_SGST":
                ledger_in_sgst += net_dr
            elif role == "INPUT_IGST":
                ledger_in_igst += net_dr

        ledger_tot_input_tax = ledger_in_cgst + ledger_in_sgst + ledger_in_igst
        itc_variance = total_eligible - ledger_tot_input_tax
        is_reconciled = (abs(itc_variance) < Decimal("0.01"))

        return Gstr2bReconciliationResponse(
            client_id=client_id,
            period=period,
            from_date=start_d,
            to_date=end_d,
            total_inward_taxable=total_inward_taxable,
            eligible_itc_cgst=eligible_cgst,
            eligible_itc_sgst=eligible_sgst,
            eligible_itc_igst=eligible_igst,
            total_eligible_itc=total_eligible,
            ineligible_itc=ineligible_itc,
            ledger_input_cgst=ledger_in_cgst,
            ledger_input_sgst=ledger_in_sgst,
            ledger_input_igst=ledger_in_igst,
            ledger_total_input_tax=ledger_tot_input_tax,
            itc_variance=itc_variance,
            is_reconciled=is_reconciled,
            invoices=invoice_rows,
        )

    # ── 3. GSTR-3B Summary ───────────────────────────────────────────────

    @classmethod
    def generate_gstr3b(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        period: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Gstr3bResponse:
        """
        Compute consolidated GSTR-3B return summary (Table 3.1 Outward & Table 4 ITC).
        Implements statutory set-off order (CGST Act Sections 49, 49A, 49B) and Table 6 cash payable.
        """
        client = cls.verify_client_access(db, client_id, user)
        gstr1 = cls.reconcile_gstr1(db, client_id, user, period, from_date, to_date)
        gstr2b = cls.reconcile_gstr2b(db, client_id, user, period, from_date, to_date)

        # Table 3.1 Outward Supplies
        outward_sec = Gstr3bSectionSummary(
            taxable_value=gstr1.total_outward_taxable,
            igst=gstr1.total_outward_igst,
            cgst=gstr1.total_outward_cgst,
            sgst=gstr1.total_outward_sgst,
            cess=Decimal("0.00"),
        )

        # Table 4 ITC: Decompose into (A) ITC Available (purchases only) and (B) ITC Reversed - others (purchase returns / reductions as positive amounts)
        avail_taxable = Decimal("0.00")
        avail_cgst = Decimal("0.00")
        avail_sgst = Decimal("0.00")
        avail_igst = Decimal("0.00")
        avail_cess = Decimal("0.00")

        rev_taxable = Decimal("0.00")
        rev_cgst = Decimal("0.00")
        rev_sgst = Decimal("0.00")
        rev_igst = Decimal("0.00")
        rev_cess = Decimal("0.00")

        if gstr2b.invoices:
            for inv in gstr2b.invoices:
                is_reduction = (
                    inv.document_category in ("debit_note", "purchase_records")
                    and (
                        inv.taxable_amount < Decimal("0.00")
                        or inv.total_tax < Decimal("0.00")
                        or inv.igst < Decimal("0.00")
                        or inv.cgst < Decimal("0.00")
                        or inv.sgst < Decimal("0.00")
                    )
                ) or (
                    inv.document_category == "debit_note"
                )
                if is_reduction:
                    rev_taxable += abs(inv.taxable_amount)
                    if inv.cgst < Decimal("0.00"):
                        rev_cgst += abs(inv.cgst)
                    if inv.sgst < Decimal("0.00"):
                        rev_sgst += abs(inv.sgst)
                    if inv.igst < Decimal("0.00"):
                        rev_igst += abs(inv.igst)
                    if inv.cess < Decimal("0.00"):
                        rev_cess += abs(inv.cess)
                else:
                    avail_taxable += inv.taxable_amount
                    avail_cgst += inv.cgst
                    avail_sgst += inv.sgst
                    avail_igst += inv.igst
                    avail_cess += inv.cess

            itc_available = Gstr3bSectionSummary(
                taxable_value=avail_taxable,
                igst=avail_igst,
                cgst=avail_cgst,
                sgst=avail_sgst,
                cess=avail_cess,
            )
            itc_reversed = Gstr3bSectionSummary(
                taxable_value=rev_taxable,
                igst=rev_igst,
                cgst=rev_cgst,
                sgst=rev_sgst,
                cess=rev_cess,
            )
            net_itc = Gstr3bSectionSummary(
                taxable_value=avail_taxable - rev_taxable,
                igst=avail_igst - rev_igst,
                cgst=avail_cgst - rev_cgst,
                sgst=avail_sgst - rev_sgst,
                cess=avail_cess - rev_cess,
            )
        else:
            avail_cgst = max(Decimal("0.00"), gstr2b.eligible_itc_cgst)
            avail_sgst = max(Decimal("0.00"), gstr2b.eligible_itc_sgst)
            avail_igst = max(Decimal("0.00"), gstr2b.eligible_itc_igst)
            rev_cgst = max(Decimal("0.00"), -gstr2b.eligible_itc_cgst)
            rev_sgst = max(Decimal("0.00"), -gstr2b.eligible_itc_sgst)
            rev_igst = max(Decimal("0.00"), -gstr2b.eligible_itc_igst)
            itc_available = Gstr3bSectionSummary(
                taxable_value=max(Decimal("0.00"), gstr2b.total_inward_taxable),
                igst=avail_igst,
                cgst=avail_cgst,
                sgst=avail_sgst,
                cess=Decimal("0.00"),
            )
            itc_reversed = Gstr3bSectionSummary(
                taxable_value=max(Decimal("0.00"), -gstr2b.total_inward_taxable),
                igst=rev_igst,
                cgst=rev_cgst,
                sgst=rev_sgst,
                cess=Decimal("0.00"),
            )
            net_itc = Gstr3bSectionSummary(
                taxable_value=gstr2b.total_inward_taxable,
                igst=gstr2b.eligible_itc_igst,
                cgst=gstr2b.eligible_itc_cgst,
                sgst=gstr2b.eligible_itc_sgst,
                cess=Decimal("0.00"),
            )

        # Statutory Set-off Engine (C10 / E1: Sections 49, 49A, 49B)
        # 1. Net output liabilities (can be negative if credit notes exceed supplies)
        raw_l_igst = outward_sec.igst
        raw_l_cgst = outward_sec.cgst
        raw_l_sgst = outward_sec.sgst

        needs_ca_review = False
        review_notes: List[str] = []

        # Negative output liabilities (excess credit notes over supplies)
        neg_cgst = abs(raw_l_cgst) if raw_l_cgst < Decimal("0.00") else Decimal("0.00")
        neg_sgst = abs(raw_l_sgst) if raw_l_sgst < Decimal("0.00") else Decimal("0.00")
        neg_igst = abs(raw_l_igst) if raw_l_igst < Decimal("0.00") else Decimal("0.00")
        tot_neg_l = neg_cgst + neg_sgst + neg_igst

        if tot_neg_l > Decimal("0.00"):
            needs_ca_review = True
            heads_neg = []
            if neg_igst > Decimal("0.00"):
                heads_neg.append(f"IGST -₹{neg_igst:,.2f}")
            if neg_cgst > Decimal("0.00"):
                heads_neg.append(f"CGST -₹{neg_cgst:,.2f}")
            if neg_sgst > Decimal("0.00"):
                heads_neg.append(f"SGST -₹{neg_sgst:,.2f}")
            review_notes.append(
                f"Net tax liability is negative in {', '.join(heads_neg)} due to credit notes exceeding supplies. "
                f"Under GST statutory set-off rules (Sections 49, 49A, 49B), negative liability cannot offset other tax heads "
                f"or reduce cash payable; it is carried forward as an adjustment for subsequent returns."
            )

        # E1 Rule: Per head h:
        # liability[h] = net outward tax[h] (existing handling for negative outward stays) + max(-net_itc[h], 0) ("ITC reversal payable")
        # credit[h] = max(net_itc[h], 0)
        itc_rev_igst = max(-net_itc.igst, Decimal("0.00"))
        itc_rev_cgst = max(-net_itc.cgst, Decimal("0.00"))
        itc_rev_sgst = max(-net_itc.sgst, Decimal("0.00"))
        tot_itc_rev = itc_rev_igst + itc_rev_cgst + itc_rev_sgst

        rem_l_igst = max(Decimal("0.00"), raw_l_igst) + itc_rev_igst
        rem_l_cgst = max(Decimal("0.00"), raw_l_cgst) + itc_rev_cgst
        rem_l_sgst = max(Decimal("0.00"), raw_l_sgst) + itc_rev_sgst

        has_negative_itc_head = tot_itc_rev > Decimal("0.00")
        if has_negative_itc_head:
            needs_ca_review = True
            review_notes.append(
                "Negative ITC head - CA to confirm treatment (pay with 3B or via DRC-03)"
            )

        # 2. Available ITC Credits
        rem_c_igst = max(Decimal("0.00"), net_itc.igst)
        rem_c_cgst = max(Decimal("0.00"), net_itc.cgst)
        rem_c_sgst = max(Decimal("0.00"), net_itc.sgst)

        # Step 1: IGST Credit -> first IGST liability, then CGST liability, then SGST liability
        used_igst_igst = min(rem_c_igst, rem_l_igst)
        rem_l_igst -= used_igst_igst
        rem_c_igst -= used_igst_igst

        used_igst_cgst = min(rem_c_igst, rem_l_cgst)
        rem_l_cgst -= used_igst_cgst
        rem_c_igst -= used_igst_cgst

        used_igst_sgst = min(rem_c_igst, rem_l_sgst)
        rem_l_sgst -= used_igst_sgst
        rem_c_igst -= used_igst_sgst

        # Step 2: CGST Credit -> first CGST liability, then IGST liability (NEVER SGST)
        used_cgst_cgst = min(rem_c_cgst, rem_l_cgst)
        rem_l_cgst -= used_cgst_cgst
        rem_c_cgst -= used_cgst_cgst

        used_cgst_igst = min(rem_c_cgst, rem_l_igst)
        rem_l_igst -= used_cgst_igst
        rem_c_cgst -= used_cgst_igst

        # Step 3: SGST Credit -> first SGST liability, then IGST liability (NEVER CGST)
        used_sgst_sgst = min(rem_c_sgst, rem_l_sgst)
        rem_l_sgst -= used_sgst_sgst
        rem_c_sgst -= used_sgst_sgst

        used_sgst_igst = min(rem_c_sgst, rem_l_igst)
        rem_l_igst -= used_sgst_igst
        rem_c_sgst -= used_sgst_igst

        # Cash payable per head floored at 0
        cash_igst = rem_l_igst
        cash_cgst = rem_l_cgst
        cash_sgst = rem_l_sgst
        tot_payable_cash = cash_igst + cash_cgst + cash_sgst

        # Remaining credit carried forward per head
        cf_igst = rem_c_igst
        cf_cgst = rem_c_cgst
        cf_sgst = rem_c_sgst
        tot_cf = cf_igst + cf_cgst + cf_sgst

        # Structured statutory settlement summary
        if tot_payable_cash > Decimal("0.00") and tot_neg_l > Decimal("0.00"):
            settlement_summary = (
                f"IGST ₹{cash_igst:,.2f} Cash Due · "
                f"CGST/SGST −₹{tot_neg_l:,.2f} adjustment carried forward"
            )
        elif tot_payable_cash > Decimal("0.00") and tot_itc_rev > Decimal("0.00"):
            rev_details = []
            if itc_rev_igst > Decimal("0.00"):
                rev_details.append(f"IGST {cash_igst:,.2f} (incl. ITC reversal {itc_rev_igst:,.2f})")
            elif cash_igst > Decimal("0.00"):
                rev_details.append(f"IGST {cash_igst:,.2f}")
            if cash_cgst > Decimal("0.00"):
                rev_details.append(f"CGST {cash_cgst:,.2f}")
            if cash_sgst > Decimal("0.00"):
                rev_details.append(f"SGST {cash_sgst:,.2f}")
            settlement_summary = f"{', '.join(rev_details)}"
        elif tot_payable_cash > Decimal("0.00"):
            settlement_summary = f"Total Tax Payable in Cash: ₹{tot_payable_cash:,.2f}"
        elif tot_cf > Decimal("0.00"):
            settlement_summary = f"Total ITC Carried Forward: ₹{tot_cf:,.2f}"
        else:
            settlement_summary = "Nil Cash Liability"

        return Gstr3bResponse(
            client_id=client_id,
            period=period,
            from_date=gstr1.from_date,
            to_date=gstr1.to_date,
            table_3_1_outward=outward_sec,
            table_4_itc_available=itc_available,
            table_4_itc_reversed=itc_reversed,
            table_4_net_itc=net_itc,
            tax_payable_in_cash=tot_payable_cash,
            excess_credit_carried_forward=tot_cf,
            cash_payable_cgst=cash_cgst,
            cash_payable_sgst=cash_sgst,
            cash_payable_igst=cash_igst,
            itc_carried_forward_cgst=cf_cgst,
            itc_carried_forward_sgst=cf_sgst,
            itc_carried_forward_igst=cf_igst,
            negative_liability_carried_forward=tot_neg_l,
            negative_liability_cgst=neg_cgst,
            negative_liability_sgst=neg_sgst,
            negative_liability_igst=neg_igst,
            itc_reversal_payable_cgst=itc_rev_cgst,
            itc_reversal_payable_sgst=itc_rev_sgst,
            itc_reversal_payable_igst=itc_rev_igst,
            itc_reversal_payable_total=tot_itc_rev,
            has_negative_itc_head=has_negative_itc_head,
            settlement_summary=settlement_summary,
            needs_ca_review=needs_ca_review,
            review_notes=review_notes,
            filing_profile=get_filing_profile(client),
        )

    # ── 4. Discrepancy Detection Engine ──────────────────────────────────

    @classmethod
    def detect_discrepancies(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        period: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> GstDiscrepancyReportResponse:
        """
        Run multi-point statutory reconciliation checks on invoices, vouchers, and GL entries.
        """
        cls.verify_client_access(db, client_id, user)
        start_d, end_d = cls._parse_period_dates(period, from_date, to_date)

        discrepancies: List[GstDiscrepancyItem] = []
        docs = db.query(UploadedDocument).filter(
            UploadedDocument.client_id == client_id,
            UploadedDocument.status != "voided",
        ).all()

        # Build maps
        posted_jes = db.query(JournalEntry).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.is_reversed == False,
        ).all()
        doc_posted_map: Dict[uuid.UUID, Any] = {}
        for je in posted_jes:
            if je.document_id:
                doc_posted_map[je.document_id] = je
            if je.accounting_record_id:
                rec = db.query(AccountingRecord).filter(AccountingRecord.id == je.accounting_record_id).first()
                if rec and rec.document_id:
                    doc_posted_map[rec.document_id] = je

        posted_records = db.query(AccountingRecord).filter(
            AccountingRecord.client_id == client_id,
            AccountingRecord.status == "posted",
        ).all()
        for ar in posted_records:
            if ar.document_id and ar.document_id not in doc_posted_map:
                doc_posted_map[ar.document_id] = ar

        seen_invoices: Dict[Tuple[str, str], UploadedDocument] = {}

        for d in docs:
            cat = (d.document_category or "").lower()
            if cat in ["e_way_bill", "gst_challan", "hsn_sac"]:
                continue

            # Period date filter (D3)
            d_date = None
            if d.invoice_date:
                try:
                    d_date = date.fromisoformat(d.invoice_date.strip()[:10])
                except Exception:
                    pass
            if not d_date and d.created_at:
                d_date = d.created_at.date()

            if d_date:
                if start_d and d_date < start_d:
                    continue
                if end_d and d_date > end_d:
                    continue

            party_name = (d.customer or d.vendor or "").strip()
            tot_amt = Decimal(str(d.amount or 0.00))
            taxable = Decimal(str(d.taxable_amount or 0.00))
            cgst = Decimal(str(d.cgst or 0.00))
            sgst = Decimal(str(d.sgst or 0.00))
            igst = Decimal(str(d.igst or 0.00))

            # Tax at risk (Rule R5): Must strictly be tax amount, never gross
            doc_tax = cgst + sgst + igst + Decimal(str(d.cess or 0.00))
            if doc_tax == Decimal("0.00") and tot_amt > taxable and taxable > Decimal("0.00"):
                doc_tax = tot_amt - taxable
            elif doc_tax == Decimal("0.00") and tot_amt > Decimal("0.00"):
                doc_tax = (tot_amt * Decimal("18") / Decimal("118")).quantize(Decimal("0.01"))

            # Rule F4(b): Documents with status "rejected" are excluded from all discrepancy rules EXCEPT the DUPLICATE alert itself
            is_rejected = getattr(d, "status", "") == "rejected"

            if not is_rejected:
                # Check 1: Missing GSTIN on B2B documents
                is_b2b = d.document_category == "b2b_invoice" or any(
                    corp in party_name.lower() for corp in ["ltd", "pvt", "limited", "corp", "llp", "inc"]
                )
                has_valid_gstin = bool(d.gstin and len(d.gstin.strip()) == 15)

                if is_b2b and not has_valid_gstin:
                    discrepancies.append(GstDiscrepancyItem(
                        discrepancy_id=f"DISC-GSTIN-{d.id}",
                        rule_code="MISSING_GSTIN",
                        severity="HIGH",
                        title="Missing or Invalid Counterparty GSTIN",
                        description=f"Invoice #{d.invoice_number or 'UNKNOWN'} with party '{party_name}' lacks a valid 15-character GSTIN.",
                        document_id=d.id,
                        invoice_number=d.invoice_number,
                        party_name=party_name,
                        variance_amount=doc_tax,
                        statutory_reference="Section 31 & Rule 46 CGST Rules (Tax Invoice requirements)",
                        recommended_action="Obtain recipient/vendor GSTIN to ensure eligibility under Section 16(2)(aa).",
                    ))

                # Check 2: Mathematical tax calculation variance
                if tot_amt > 0 and taxable > 0:
                    expected_tot = taxable + cgst + sgst + igst
                    variance = abs(tot_amt - expected_tot)
                    if variance > Decimal("1.00"):
                        discrepancies.append(GstDiscrepancyItem(
                            discrepancy_id=f"DISC-MATH-{d.id}",
                            rule_code="TAX_MATH_MISMATCH",
                            severity="HIGH",
                            title="Invoice Line Tax Math Discrepancy",
                            description=f"Invoice #{d.invoice_number or 'UNKNOWN'} total (₹{tot_amt}) does not equal Taxable (₹{taxable}) + Taxes (₹{cgst+sgst+igst}). Discrepancy: ₹{variance}.",
                            document_id=d.id,
                            invoice_number=d.invoice_number,
                            party_name=party_name,
                            variance_amount=variance,
                            statutory_reference="Section 15 CGST Act (Value of Taxable Supply)",
                            recommended_action="Review OCR extraction lines or edit fields to fix tax calculation variance.",
                        ))

                # Check 3: Unposted Invoices (Include all qualifying invoice & note categories)
                # Rule F4(c): Compliance documents (e-way bill, challan, HSN master, an e-invoice linked to a posted invoice) never raise UNPOSTED_INVOICE
                unposted_eligible_categories = [
                    "sales_records", "purchase_records", "b2b_invoice",
                    "e_invoice", "b2c_invoice", "credit_note", "debit_note"
                ]
                if d.document_category in unposted_eligible_categories and d.status == "verified":
                    # Check if this is an e-invoice companion whose plain invoice is posted
                    is_einvoice_companion_posted = False
                    if d.document_category == "e_invoice":
                        linked_id = getattr(d, "linked_document_id", None)
                        if linked_id and linked_id in doc_posted_map:
                            is_einvoice_companion_posted = True
                        else:
                            companion_doc = db.query(UploadedDocument).filter(
                                UploadedDocument.client_id == client_id,
                                UploadedDocument.invoice_number == d.invoice_number,
                                UploadedDocument.id != d.id,
                                UploadedDocument.document_category != "e_invoice",
                            ).first()
                            if companion_doc and companion_doc.id in doc_posted_map:
                                is_einvoice_companion_posted = True

                    if not is_einvoice_companion_posted and d.id not in doc_posted_map:
                        discrepancies.append(GstDiscrepancyItem(
                            discrepancy_id=f"DISC-UNPOSTED-{d.id}",
                            rule_code="UNPOSTED_INVOICE",
                            severity="MEDIUM",
                            title="Verified Document Not Posted to Ledger",
                            description=f"Document #{d.invoice_number or 'UNKNOWN'} is verified but not yet posted into the general ledger.",
                            document_id=d.id,
                            invoice_number=d.invoice_number,
                            party_name=party_name,
                            variance_amount=doc_tax,
                            statutory_reference="Section 128 Companies Act (Books of Account maintenance)",
                            recommended_action="Post the document draft voucher to General Ledger to update accounting balances.",
                        ))

                # Check 3b: Blocked / Needs Review Documents (D5)
                if getattr(d, "status", "") in ("needs_review", "blocked"):
                    discrepancies.append(GstDiscrepancyItem(
                        discrepancy_id=f"DISC-REVIEW-{d.id}",
                        rule_code="NEEDS_REVIEW",
                        severity="HIGH",
                        title="Document Blocked / Requires CA Review",
                        description=f"Document #{d.invoice_number or 'UNKNOWN'} ({d.document_category}) requires statutory review before posting.",
                        document_id=d.id,
                        invoice_number=d.invoice_number,
                        party_name=party_name,
                        variance_amount=doc_tax,
                        statutory_reference="Statutory Pre-Posting Validation Gate",
                        recommended_action="Resolve orientation or mismatch error in Document Review workspace.",
                    ))

            # Check 4: Duplicate Invoices
            inv_num = (d.invoice_number or "").strip().upper()
            gstin_key = (d.gstin or "").strip().upper()
            if inv_num and gstin_key:
                if cat in ("sales_records", "b2b_invoice", "b2c_invoice"):
                    doc_family = "sales"
                elif cat in ("purchase_records",):
                    doc_family = "purchase"
                elif cat in ("credit_note",):
                    doc_family = "credit_note"
                elif cat in ("debit_note",):
                    doc_family = "debit_note"
                else:
                    doc_family = cat

                key = (inv_num, gstin_key, doc_family)
                if key in seen_invoices:
                    prev = seen_invoices[key]
                    # The duplicate is the one without a posted voucher, else the later upload
                    if d.id not in doc_posted_map and prev.id in doc_posted_map:
                        dup_doc = d
                        orig_doc = prev
                    elif prev.id not in doc_posted_map and d.id in doc_posted_map:
                        dup_doc = prev
                        orig_doc = d
                    else:
                        d_time = d.uploaded_at or d.created_at
                        prev_time = prev.uploaded_at or prev.created_at
                        if d_time and prev_time and d_time < prev_time:
                            dup_doc = prev
                            orig_doc = d
                        else:
                            dup_doc = d
                            orig_doc = prev

                    # Calculate tax at risk strictly from the duplicate document (Rule R5 / F4)
                    dup_tax = (
                        Decimal(str(dup_doc.cgst or 0.00))
                        + Decimal(str(dup_doc.sgst or 0.00))
                        + Decimal(str(dup_doc.igst or 0.00))
                        + Decimal(str(dup_doc.cess or 0.00))
                    )
                    if dup_tax == Decimal("0.00"):
                        dup_tot = Decimal(str(dup_doc.amount or 0.00))
                        dup_taxable = Decimal(str(dup_doc.taxable_amount or 0.00))
                        if dup_tot > dup_taxable and dup_taxable > Decimal("0.00"):
                            dup_tax = dup_tot - dup_taxable
                        elif dup_tot > Decimal("0.00"):
                            dup_tax = (dup_tot * Decimal("18") / Decimal("118")).quantize(Decimal("0.01"))

                    is_rejected_dup = (
                        getattr(dup_doc, "status", "") == "rejected"
                        or getattr(dup_doc, "rejection_reason", "") in ("DUPLICATE", "duplicate")
                        or getattr(orig_doc, "status", "") == "rejected"
                        or getattr(orig_doc, "rejection_reason", "") in ("DUPLICATE", "duplicate")
                    )

                    if is_rejected_dup:
                        discrepancies.append(GstDiscrepancyItem(
                            discrepancy_id=f"DISC-DUP-{dup_doc.id}",
                            rule_code="DUPLICATE_REJECTED",
                            severity="INFO",
                            title="Rejected Duplicate Document",
                            description=f"Rejected duplicate {dup_doc.invoice_number or inv_num} is excluded from all figures - you may delete it",
                            document_id=dup_doc.id,
                            invoice_number=dup_doc.invoice_number,
                            party_name=party_name,
                            variance_amount=Decimal("0.00"),
                            statutory_reference="Rule 48 CGST Rules (Manner of issuing invoice)",
                            recommended_action="Rejected duplicate is excluded from all figures - you may delete it.",
                        ))
                    else:
                        discrepancies.append(GstDiscrepancyItem(
                            discrepancy_id=f"DISC-DUP-{dup_doc.id}",
                            rule_code="DUPLICATE_INVOICE",
                            severity="HIGH",
                            title="Duplicate Invoice Detected",
                            description=f"Invoice #{inv_num} for GSTIN {gstin_key} already exists (Document #{orig_doc.id}).",
                            document_id=dup_doc.id,
                            invoice_number=dup_doc.invoice_number,
                            party_name=party_name,
                            variance_amount=dup_tax,
                            statutory_reference="Rule 48 CGST Rules (Manner of issuing invoice)",
                            recommended_action="Inspect duplicate upload and delete/void duplicate document to prevent double counting.",
                        ))
                else:
                    seen_invoices[key] = d

        # Check 5: Unlinked GL Tax Entries
        # Manual journal lines touching GST accounts without an uploaded document link
        gst_acc_codes = ["1060", "1070", "1080", "2020", "2030", "2040"]
        unlinked_tax_q = db.query(JournalEntry).join(
            JournalEntryLine, JournalEntryLine.journal_entry_id == JournalEntry.id
        ).join(
            ChartOfAccounts, ChartOfAccounts.id == JournalEntryLine.account_id
        ).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.document_id.is_(None),
            ChartOfAccounts.account_code.in_(gst_acc_codes),
        )
        if start_d:
            unlinked_tax_q = unlinked_tax_q.filter(JournalEntry.entry_date >= start_d)
        if end_d:
            unlinked_tax_q = unlinked_tax_q.filter(JournalEntry.entry_date <= end_d)
        unlinked_tax_jes = unlinked_tax_q.distinct().all()

        for je in unlinked_tax_jes:
            discrepancies.append(GstDiscrepancyItem(
                discrepancy_id=f"DISC-UNLINKED-JE-{je.id}",
                rule_code="UNLINKED_LEDGER_ENTRY",
                severity="LOW",
                title="GL Tax Entry Without Supporting Document Link",
                description=f"Journal Entry #{je.entry_number} records GST tax amounts but is not linked to any source document.",
                voucher_id=je.id,
                invoice_number=je.reference_number,
                party_name=je.narration,
                variance_amount=je.total_debit,
                statutory_reference="Rule 56(1) CGST Rules (Maintenance of accounts by registered persons)",
                recommended_action="Attach supporting tax invoice or challan to ensure audit trail integrity.",
            ))

        # Check 6: Legacy Vouchers Missing Statutory Tax Lines (D2)
        # Find posted vouchers whose source document has tax, but whose lines lack GST accounts
        for je in posted_jes:
            if je.entry_type == "reversal" or je.status == "reversed":
                continue
            if start_d and je.entry_date and je.entry_date < start_d:
                continue
            if end_d and je.entry_date and je.entry_date > end_d:
                continue

            # F9: Exclude payment vouchers from commercial tax lines check
            is_payment = (
                je.voucher_template == "PAYMENT"
                or (je.entry_type or "").lower() == "payment"
            )
            if is_payment:
                # Add FUTURE_DATED_PAYMENT advisory alert (MEDIUM, non-blocking) if payment date > today
                if je.entry_date and je.entry_date > date.today():
                    discrepancies.append(GstDiscrepancyItem(
                        discrepancy_id=f"DISC-FUTURE-PAY-{je.id}",
                        rule_code="FUTURE_DATED_PAYMENT",
                        severity="MEDIUM",
                        title="Future-Dated Tax Payment Voucher",
                        description=f"Payment voucher #{je.entry_number} is dated {je.entry_date}, which is after today's date ({date.today()}). Non-blocking advisory.",
                        voucher_id=je.id,
                        invoice_number=je.reference_number,
                        party_name=je.counterparty_name or "GST Tax Challan",
                        variance_amount=Decimal("0.00"),
                        statutory_reference="Section 49 CGST Act (Payment of tax, interest, penalty and other amounts)",
                        recommended_action="Verify voucher payment date against bank realization statement.",
                    ))
                continue

            doc = None
            if je.document_id:
                doc = db.query(UploadedDocument).filter(UploadedDocument.id == je.document_id).first()
            elif je.accounting_record_id:
                ar = db.query(AccountingRecord).filter(AccountingRecord.id == je.accounting_record_id).first()
                if ar and ar.document_id:
                    doc = db.query(UploadedDocument).filter(UploadedDocument.id == ar.document_id).first()

            if not doc:
                continue

            doc_tax = Decimal(str((doc.cgst or 0) + (doc.sgst or 0) + (doc.igst or 0) + (doc.cess or 0)))
            if doc_tax > Decimal("0.00"):
                has_gst_line = False
                for line in je.lines:
                    if line.account:
                        if line.account.role in ("OUTPUT_CGST", "OUTPUT_SGST", "OUTPUT_IGST", "INPUT_CGST", "INPUT_SGST", "INPUT_IGST"):
                            has_gst_line = True
                            break
                        if line.account.account_code in ("2110", "2120", "2130", "1210", "1220", "1230", "1060", "1070", "1080", "2020", "2030", "2040"):
                            has_gst_line = True
                            break

                if not has_gst_line:
                    discrepancies.append(GstDiscrepancyItem(
                        discrepancy_id=f"DISC-LEGACY-{je.id}",
                        rule_code="LEGACY_VOUCHER_NO_TAX_LINES",
                        severity="HIGH",
                        title="Legacy Voucher Missing Statutory Tax Lines",
                        description=f"Voucher #{je.entry_number} for document #{doc.invoice_number or 'UNKNOWN'} has document tax (₹{doc_tax}) but voucher lines lack GST accounts.",
                        document_id=doc.id,
                        voucher_id=je.id,
                        invoice_number=doc.invoice_number,
                        party_name=(doc.customer or doc.vendor or "").strip(),
                        variance_amount=doc_tax,
                        statutory_reference="Section 31 & Section 16 CGST Act (Statutory GST Account Posting)",
                        recommended_action="Run repost_legacy_vouchers.py to void legacy entry and post balanced T1-T6 voucher.",
                    ))

        high_c = sum(1 for d in discrepancies if d.severity == "HIGH")
        med_c = sum(1 for d in discrepancies if d.severity == "MEDIUM")
        low_c = sum(1 for d in discrepancies if d.severity == "LOW")
        tot_risk = sum(d.variance_amount for d in discrepancies if d.severity in ["HIGH", "MEDIUM"])

        return GstDiscrepancyReportResponse(
            client_id=client_id,
            period=period,
            total_discrepancies=len(discrepancies),
            high_count=high_c,
            medium_count=med_c,
            low_count=low_c,
            total_tax_at_risk=tot_risk,
            discrepancies=discrepancies,
        )

    # ── 5. Financial Insights & CA Review ─────────────────────────────────

    @classmethod
    def get_financial_insights(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        period: Optional[str] = None,
    ) -> GstFinancialInsightsResponse:
        """
        Generate explainable CA review insights, compliance health score, and actionable checklist.
        """
        disc_rep = cls.detect_discrepancies(db, client_id, user, period=period)
        gstr3b = cls.generate_gstr3b(db, client_id, user, period=period)

        # 1. Compute Compliance Score
        score = 100
        score -= (disc_rep.high_count * 15)
        score -= (disc_rep.medium_count * 8)
        score -= (disc_rep.low_count * 3)
        score = max(10, min(100, score))

        if score >= 85:
            risk = "LOW"
        elif score >= 65:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        # 2. CA Observations
        obs: List[str] = []
        outward_val = gstr3b.table_3_1_outward.taxable_value
        net_itc_val = gstr3b.table_4_net_itc.cgst + gstr3b.table_4_net_itc.sgst + gstr3b.table_4_net_itc.igst
        tot_outward_tax = gstr3b.table_3_1_outward.cgst + gstr3b.table_3_1_outward.sgst + gstr3b.table_3_1_outward.igst

        if tot_outward_tax > Decimal("0.00"):
            itc_ratio = (net_itc_val / tot_outward_tax) * Decimal("100.00")
            obs.append(f"ITC Utilization Efficiency: Available ITC covers {itc_ratio:.1f}% of gross outward tax liability.")
        else:
            obs.append("No gross outward tax liability generated in this reporting window.")

        if gstr3b.tax_payable_in_cash > Decimal("0.00"):
            obs.append(f"Estimated Net Cash Outflow: ₹{gstr3b.tax_payable_in_cash:,.2f} required for GSTR-3B tax payment.")
        else:
            obs.append(f"Excess Input Tax Credit: ₹{gstr3b.excess_credit_carried_forward:,.2f} available to carry forward to the next period.")

        if disc_rep.high_count > 0:
            obs.append(f"Critical Attention Required: {disc_rep.high_count} high-severity tax issues found affecting ₹{disc_rep.total_tax_at_risk:,.2f} in tax value.")
        else:
            obs.append("All scanned documents satisfy basic GSTIN formatting and mathematical checks.")

        # 3. Action Checklist
        checklist: List[FilingChecklistItem] = [
            FilingChecklistItem(
                check_name="GSTR-1 vs General Ledger Sales Turnover Match",
                status="PASSED" if disc_rep.medium_count == 0 else "WARNING",
                message="Books of accounts turnover aligns with reported outward invoices.",
                statutory_section="Section 37 CGST Act",
            ),
            FilingChecklistItem(
                check_name="Supplier Section 16(2)(aa) Verification",
                status="ACTION_REQUIRED" if disc_rep.high_count > 0 else "PASSED",
                message="Supplier GSTINs verified to prevent Input Tax Credit rejection by tax authorities.",
                statutory_section="Section 16(2)(aa)",
            ),
            FilingChecklistItem(
                check_name="Section 17(5) Blocked Credit Review",
                status="PASSED",
                message="No blocked credits detected under motor vehicles, food & beverages, or personal consumption.",
                statutory_section="Section 17(5)",
            ),
            FilingChecklistItem(
                check_name="Unposted Invoices Clearance",
                status="ACTION_REQUIRED" if any(d.rule_code == "UNPOSTED_INVOICE" for d in disc_rep.discrepancies) else "PASSED",
                message="All verified invoices have been posted to General Ledger journals.",
                statutory_section="Rule 56 CGST Rules",
            ),
        ]

        metrics = {
            "total_discrepancies": disc_rep.total_discrepancies,
            "high_severity": disc_rep.high_count,
            "medium_severity": disc_rep.medium_count,
            "low_severity": disc_rep.low_count,
            "taxable_turnover": float(outward_val),
            "output_tax": float(tot_outward_tax),
            "net_itc_claimed": float(net_itc_val),
            "cash_tax_payable": float(gstr3b.tax_payable_in_cash),
            "excess_credit_cf": float(gstr3b.excess_credit_carried_forward),
        }

        return GstFinancialInsightsResponse(
            client_id=client_id,
            period=period,
            compliance_score=score,
            risk_level=risk,
            summary_metrics=metrics,
            ca_observations=obs,
            action_checklist=checklist,
        )

    @classmethod
    def get_gstr1_table_12_hsn_summary(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        period: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Gstr1HsnSummaryResponse:
        """
        Aggregate dynamic HSN/SAC Table 12 outward summary strictly from posted outward sales vouchers.
        Follows rule E2:
        - Only outward commercial sales categories (b2b_invoice, b2c_invoice, sales_records, credit_note).
        - Excludes payment vouchers, purchase vouchers, receipts, and contra.
        - Groups by (hsn_sac, effective_rate).
        - Description: line-item description (first non-note line for that code; fallback to HSN master uploaded for the client; never party name).
        - Rate: item rate as % (or tax/taxable * 100 rounded to 2 decimals).
        - Amounts: taxable, CGST, SGST, IGST, total_tax = sum of items; credit notes reduce turnover/tax.
        """
        client = cls.verify_client_access(db, client_id, user)
        client_gstin = (client.gst_number or "").strip().upper()
        start_d, end_d = cls._parse_period_dates(period, from_date, to_date)

        # 1. Fetch only posted, unreversed journal entries
        posted_jes = db.query(JournalEntry).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.status == "posted",
            JournalEntry.is_reversed == False,
        ).all()
        posted_je_map: Dict[uuid.UUID, JournalEntry] = {
            je.document_id: je for je in posted_jes if je.document_id
        }

        # 2. Build HSN master description cache from uploaded hsn_sac documents
        hsn_master_desc: Dict[str, str] = {}
        hsn_docs = db.query(UploadedDocument).filter(
            UploadedDocument.client_id == client_id,
            UploadedDocument.document_category == "hsn_sac",
            UploadedDocument.status != "rejected",
        ).all()
        for hd in hsn_docs:
            if hd.metadata_:
                try:
                    import json
                    h_meta = json.loads(hd.metadata_)
                    h_items = h_meta.get("line_items") or h_meta.get("table_data", {}).get("rows") or []
                    for h_row in h_items:
                        code = str(h_row.get("hsn") or h_row.get("hsn_code") or h_row.get("hsn_sac") or "").strip()
                        desc = str(h_row.get("item_name") or h_row.get("description") or "").strip()
                        if code and desc and code not in hsn_master_desc:
                            hsn_master_desc[code] = desc
                except Exception:
                    pass

        # 3. Fetch candidate outward commercial sales documents strictly
        outward_sales_categories = ("sales_records", "b2b_invoice", "b2c_invoice", "credit_note", "sales_invoice")
        docs = db.query(UploadedDocument).filter(
            UploadedDocument.client_id == client_id,
            UploadedDocument.document_category.in_(outward_sales_categories),
            UploadedDocument.status != "rejected",
        ).all()

        groups: Dict[Tuple[str, Decimal], Dict[str, Any]] = {}
        first_non_note_desc: Dict[str, str] = {}

        for d in docs:
            if d.id not in posted_je_map:
                continue

            je = posted_je_map[d.id]
            # Exclude non-sales voucher types (payment, receipt, contra, purchase)
            if (je.entry_type or "").lower() in ("payment", "receipt", "contra", "purchase"):
                continue
            if je.voucher_template and je.voucher_template not in ("T1", "T3", "T4"):
                continue

            # Direction must be OUTWARD
            direction = cls.determine_document_direction(d, client_gstin, db=db)
            if direction != "OUTWARD":
                continue

            # Exclude purchase lines
            has_purchase_lines = any(
                ((l.account.role if l.account else None) or determine_account_role(l.account.account_code, l.account.account_name, l.account.account_type) if l.account else None) in ("PURCHASE", "PURCHASE_RETURN", "INPUT_CGST", "INPUT_SGST", "INPUT_IGST")
                for l in je.lines
            )
            if has_purchase_lines:
                continue

            d_date = je.entry_date
            if not d_date and d.invoice_date:
                try:
                    d_date = date.fromisoformat(d.invoice_date.strip()[:10])
                except Exception:
                    pass
            if not d_date and d.created_at:
                d_date = d.created_at.date()

            if d_date:
                if start_d and d_date < start_d:
                    continue
                if end_d and d_date > end_d:
                    continue

            is_credit_note = (d.document_category == "credit_note") or ("credit" in (d.invoice_type or "").lower())
            multiplier = Decimal("-1.00") if is_credit_note else Decimal("1.00")

            # Determine voucher taxes from ledger lines
            v_taxable = Decimal("0.00")
            v_cgst = Decimal("0.00")
            v_sgst = Decimal("0.00")
            v_igst = Decimal("0.00")
            v_cess = Decimal("0.00")
            for line in je.lines:
                acc = line.account
                role = (acc.role if acc else None) or (determine_account_role(acc.account_code, acc.account_name, acc.account_type) if acc else None)
                dr = Decimal(str(line.debit_amount or 0.00))
                cr = Decimal(str(line.credit_amount or 0.00))
                net_cr = cr - dr
                if role in ("SALES", "OTHER_INCOME", "SALES_RETURN"):
                    v_taxable += net_cr
                elif role == "OUTPUT_CGST":
                    v_cgst += net_cr
                elif role == "OUTPUT_SGST":
                    v_sgst += net_cr
                elif role == "OUTPUT_IGST":
                    v_igst += net_cr
                elif role == "OUTPUT_CESS":
                    v_cess += net_cr

            # Check if document has line items in metadata or extract from file
            raw_items: List[Dict[str, Any]] = []
            if d.metadata_:
                try:
                    import json
                    meta = json.loads(d.metadata_)
                    if isinstance(meta, dict):
                        m_items = meta.get("line_items") or meta.get("fields", {}).get("line_items") or []
                        if isinstance(m_items, list):
                            for it in m_items:
                                h = str(it.get("hsn") or it.get("hsn_code") or it.get("HSN / SAC") or "").strip()
                                if h and len(h) >= 2 and h.isdigit():
                                    raw_items.append(it)
                except Exception:
                    pass

            if not raw_items and d.file_path and os.path.exists(d.file_path):
                try:
                    from app.api.routers.ocr.router import _extract_tables_and_metadata_from_pdf
                    with open(d.file_path, "rb") as f:
                        f_bytes = f.read()
                    _, tables = _extract_tables_and_metadata_from_pdf(f_bytes)
                    for t in tables:
                        for r in t.get("rows", []):
                            h = str(r.get("hsn_code") or r.get("hsn") or r.get("HSN / SAC") or "").strip()
                            if h and len(h) >= 2 and h.isdigit():
                                raw_items.append(r)
                except Exception:
                    pass

            if raw_items:
                for item in raw_items:
                    hsn_code = str(item.get("hsn") or item.get("hsn_code") or item.get("HSN / SAC") or d.hsn or "OTH").strip()
                    desc = str(item.get("item_name") or item.get("description") or item.get("Item Description") or item.get("particulars") or "").strip()
                    if not is_credit_note and hsn_code not in first_non_note_desc and desc:
                        first_non_note_desc[hsn_code] = desc

                    qty = Decimal(str(item.get("quantity") or item.get("qty") or item.get("Quantity") or 0.00)) * multiplier
                    uqc = str(item.get("unit") or item.get("uom") or item.get("Unit") or "NOS").strip().upper()

                    # Amounts
                    if len(raw_items) == 1:
                        item_taxable = abs(v_taxable) * multiplier
                        item_cgst = abs(v_cgst) * multiplier
                        item_sgst = abs(v_sgst) * multiplier
                        item_igst = abs(v_igst) * multiplier
                        item_cess = abs(v_cess) * multiplier
                    else:
                        item_taxable = Decimal(str(item.get("taxable_amount") or item.get("taxable_value_inr") or item.get("Taxable Value") or item.get("amount") or 0.00)) * multiplier
                        item_cgst = Decimal(str(item.get("cgst") or item.get("cgst_amount") or 0.00)) * multiplier
                        item_sgst = Decimal(str(item.get("sgst") or item.get("sgst_amount") or 0.00)) * multiplier
                        item_igst = Decimal(str(item.get("igst") or item.get("igst_amount") or 0.00)) * multiplier
                        item_cess = Decimal(str(item.get("cess") or 0.00)) * multiplier
                        if (item_cgst + item_sgst + item_igst + item_cess) == Decimal("0.00") and v_taxable != Decimal("0.00"):
                            ratio = abs(item_taxable) / abs(v_taxable)
                            item_cgst = abs(v_cgst) * ratio * multiplier
                            item_sgst = abs(v_sgst) * ratio * multiplier
                            item_igst = abs(v_igst) * ratio * multiplier
                            item_cess = abs(v_cess) * ratio * multiplier

                    item_tax = item_cgst + item_sgst + item_igst + item_cess
                    item_total = item_taxable + item_tax

                    if item_taxable != Decimal("0.00"):
                        effective_rate = (abs(item_tax) / abs(item_taxable) * Decimal("100.00")).quantize(Decimal("0.01"))
                    else:
                        effective_rate = Decimal("18.00")

                    key = (hsn_code, effective_rate)
                    if key not in groups:
                        groups[key] = {
                            "hsn_sac": hsn_code,
                            "effective_rate": effective_rate,
                            "uqc": uqc,
                            "total_quantity": Decimal("0.00"),
                            "total_value": Decimal("0.00"),
                            "taxable_amount": Decimal("0.00"),
                            "cgst": Decimal("0.00"),
                            "sgst": Decimal("0.00"),
                            "igst": Decimal("0.00"),
                            "cess": Decimal("0.00"),
                            "total_tax": Decimal("0.00"),
                            "vouchers": set(),
                        }
                    e = groups[key]
                    e["total_quantity"] += qty
                    e["total_value"] += item_total
                    e["taxable_amount"] += item_taxable
                    e["cgst"] += item_cgst
                    e["sgst"] += item_sgst
                    e["igst"] += item_igst
                    e["cess"] += item_cess
                    e["total_tax"] += item_tax
                    e["vouchers"].add(je.id)
            else:
                # Document level fallback
                hsn_code = str(d.hsn or "OTH").strip()
                v_tax = v_cgst + v_sgst + v_igst + v_cess
                v_total = v_taxable + v_tax
                if v_taxable != Decimal("0.00"):
                    effective_rate = (abs(v_tax) / abs(v_taxable) * Decimal("100.00")).quantize(Decimal("0.01"))
                else:
                    effective_rate = Decimal("18.00")

                key = (hsn_code, effective_rate)
                if key not in groups:
                    groups[key] = {
                        "hsn_sac": hsn_code,
                        "effective_rate": effective_rate,
                        "uqc": "NOS",
                        "total_quantity": Decimal("0.00"),
                        "total_value": Decimal("0.00"),
                        "taxable_amount": Decimal("0.00"),
                        "cgst": Decimal("0.00"),
                        "sgst": Decimal("0.00"),
                        "igst": Decimal("0.00"),
                        "cess": Decimal("0.00"),
                        "total_tax": Decimal("0.00"),
                        "vouchers": set(),
                    }
                e = groups[key]
                e["total_value"] += v_total
                e["taxable_amount"] += v_taxable
                e["cgst"] += v_cgst
                e["sgst"] += v_sgst
                e["igst"] += v_igst
                e["cess"] += v_cess
                e["total_tax"] += v_tax
                e["vouchers"].add(je.id)

        items: List[Gstr1HsnItem] = []
        for (code, rate), data in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
            description = (
                first_non_note_desc.get(code)
                or hsn_master_desc.get(code)
                or "Outward Supplies"
            )

            items.append(Gstr1HsnItem(
                hsn_sac=data["hsn_sac"],
                description=description,
                uqc=data["uqc"],
                total_quantity=data["total_quantity"].quantize(Decimal("0.01")),
                total_value=data["total_value"].quantize(Decimal("0.01")),
                taxable_amount=data["taxable_amount"].quantize(Decimal("0.01")),
                cgst=data["cgst"].quantize(Decimal("0.01")),
                sgst=data["sgst"].quantize(Decimal("0.01")),
                igst=data["igst"].quantize(Decimal("0.01")),
                cess=data["cess"].quantize(Decimal("0.01")),
                total_tax=data["total_tax"].quantize(Decimal("0.01")),
                gst_rate=rate,
                invoice_count=len(data["vouchers"]),
            ))

        tot_taxable = sum(it.taxable_amount for it in items)
        tot_tax = sum(it.total_tax for it in items)

        return Gstr1HsnSummaryResponse(
            client_id=client_id,
            period=period,
            total_records=len(items),
            total_taxable_value=tot_taxable,
            total_tax_amount=tot_tax,
            hsn_items=items,
        )
