"""
Accounting Mapping Service — Translates Verified Documents into Balanced Double-Entry Journal Lines.
Resolves persistent ChartOfAccounts accounts for the client.
Adheres to ICAI guidelines and Indian GST statutory rules.
"""

import uuid
import logging
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from datetime import date

from sqlalchemy.orm import Session

from app.models.uploaded_document import UploadedDocument
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.user import User
from app.services.chart_of_accounts_service import ChartOfAccountsService
from app.schemas.journal_entry import JournalEntryCreate, JournalEntryLineCreate
from app.core.exceptions import BadRequestException

logger = logging.getLogger(__name__)



class AccountingMappingService:

    @classmethod
    def get_or_init_client_accounts(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
    ) -> Dict[str, ChartOfAccounts]:
        """
        Retrieve client Chart of Accounts mapped by account_code.
        If client has no accounts yet, automatically and idempotently initializes the 26 ICAI accounts.
        """
        accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()
        if not accounts:
            logger.info("Client %s has no Chart of Accounts; auto-initializing default accounts", client_id)
            ChartOfAccountsService.initialize_default_accounts(db, client_id, user)
            accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.client_id == client_id).all()

        return {acc.account_code: acc for acc in accounts}

    @classmethod
    def map_document_to_journal_entry(
        cls,
        db: Session,
        doc: UploadedDocument,
        user: User,
        allow_client_mismatch: bool = False,
    ) -> JournalEntryCreate:
        """
        Translate a verified UploadedDocument into a strictly balanced JournalEntryCreate payload.
        Resolves persistent account_id foreign keys from client's Chart of Accounts.
        """
        if doc.status != "verified":
            raise BadRequestException(detail=f"Document {doc.id} must be verified before journal posting")

        if doc.amount is None or doc.amount <= Decimal("0"):
            raise BadRequestException(detail=f"Document {doc.id} must have an amount greater than 0")

        acc_map = cls.get_or_init_client_accounts(db, doc.client_id, user)
        accounts_list = list(acc_map.values())

        def get_acc(role_name: str, *fallback_codes: str) -> Optional[ChartOfAccounts]:
            for a in accounts_list:
                if getattr(a, "role", None) == role_name:
                    return a
            for code in fallback_codes:
                if code in acc_map:
                    return acc_map[code]
            return None

        from app.models.client import Client
        client = db.query(Client).filter(Client.id == doc.client_id).first()
        client_gstin = (client.gst_number or "").strip().upper() if client else ""

        cat = (doc.document_category or "").lower()
        gross_amount = Decimal(str(doc.amount)).quantize(Decimal("0.01"))
        cgst = Decimal(str(doc.cgst)).quantize(Decimal("0.01")) if doc.cgst else Decimal("0.00")
        sgst = Decimal(str(doc.sgst)).quantize(Decimal("0.01")) if doc.sgst else Decimal("0.00")
        igst = Decimal(str(doc.igst)).quantize(Decimal("0.01")) if doc.igst else Decimal("0.00")
        cess = Decimal(str(doc.cess)).quantize(Decimal("0.01")) if doc.cess else Decimal("0.00")
        tot_tax = cgst + sgst + igst + cess

        # ── 1. Validate Component Sum vs Printed Total ────────────────────────
        if doc.taxable_amount is not None:
            taxable_amount = Decimal(str(doc.taxable_amount)).quantize(Decimal("0.01"))
            expected_total = taxable_amount + tot_tax
            diff_math = abs(gross_amount - expected_total)
            if diff_math > Decimal("0.05"):
                raise BadRequestException(
                    detail=f"Posting blocked: Sum of components (taxable ₹{taxable_amount} + taxes ₹{tot_tax} = ₹{expected_total}) "
                           f"differs from printed total (₹{gross_amount}) by ₹{diff_math}."
                )
        else:
            if tot_tax > Decimal("0.00"):
                taxable_amount = gross_amount - tot_tax
                if taxable_amount < Decimal("0.00"):
                    raise BadRequestException(
                        detail=f"Posting blocked: Taxes (₹{tot_tax}) exceed printed total (₹{gross_amount})."
                    )
            else:
                taxable_amount = gross_amount

        # ── 2. Decide Direction from Issuer and Client's GSTIN ─────────────────
        meta_supplier_gstin = ""
        meta_customer_gstin = ""
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
            except Exception:
                pass

        doc_gstin = (doc.gstin or "").strip().upper()

        # C3: Check Client GSTIN Anchor & CLIENT_MISMATCH
        if client_gstin and not allow_client_mismatch:
            if meta_supplier_gstin and meta_customer_gstin:
                if meta_supplier_gstin != client_gstin and meta_customer_gstin != client_gstin:
                    raise BadRequestException(
                        detail=f"CLIENT_MISMATCH: Document does not belong to this client. "
                               f"Supplier GSTIN ({meta_supplier_gstin}) and Recipient GSTIN ({meta_customer_gstin}) "
                               f"both differ from Client GSTIN ({client_gstin})."
                    )
            elif meta_supplier_gstin and not meta_customer_gstin:
                if meta_supplier_gstin != client_gstin and cat in {"sales_records", "b2c_invoice"}:
                    raise BadRequestException(
                        detail=f"CLIENT_MISMATCH: Document does not belong to this client. "
                               f"Sales invoice supplier ({meta_supplier_gstin}) does not match Client ({client_gstin})."
                    )
            elif meta_customer_gstin and not meta_supplier_gstin:
                if meta_customer_gstin != client_gstin and cat in {"purchase_records"}:
                    raise BadRequestException(
                        detail=f"CLIENT_MISMATCH: Document does not belong to this client. "
                               f"Purchase invoice recipient ({meta_customer_gstin}) does not match Client ({client_gstin})."
                    )

        # Decide direction
        is_outward = False
        is_inward = False

        if cat in {"credit_note", "debit_note"}:
            # Notes issued by client or received: resolve sales-side vs purchase-side
            note_side = None

            # (1) Look up referenced original invoice ("Against Invoice X dt Y")
            ocr_content = getattr(doc, "ocr_text", "") or ""
            extr_content = getattr(doc, "extracted_text", "") or ""
            raw_text_content = f"{ocr_content} {extr_content} {doc.metadata_ or ''}"
            import re
            from sqlalchemy import func
            m_ref = re.search(r"(?:Against|Ref(?:erence)?|Original)\s+(?:Invoice|Inv)?\.?\s*[:\-]?\s*([A-Za-z0-9\/\-_]+)", raw_text_content, re.IGNORECASE)
            ref_inv_no = m_ref.group(1).strip() if m_ref else ""

            if ref_inv_no:
                orig_doc = db.query(UploadedDocument).filter(
                    UploadedDocument.client_id == doc.client_id,
                    func.upper(UploadedDocument.invoice_number) == ref_inv_no.upper(),
                ).first()
                if orig_doc:
                    orig_cat = (orig_doc.document_category or "").lower()
                    if orig_cat in {"sales_records", "b2c_invoice", "b2b_invoice"} or "sales" in (orig_doc.invoice_type or "").lower():
                        note_side = "SALES"
                    elif orig_cat in {"purchase_records"} or "purchase" in (orig_doc.invoice_type or "").lower():
                        note_side = "PURCHASE"

            # (2) Hint from applies_to, category or text
            if not note_side:
                if getattr(doc, "applies_to", None):
                    applies = str(doc.applies_to).strip().upper()
                    if applies in ("SALES", "PURCHASE"):
                        note_side = applies
                if not note_side and ("purchase" in cat or "purchase" in raw_text_content.lower() or (doc.invoice_type and "purchase" in doc.invoice_type.lower())):
                    note_side = "PURCHASE"
                elif "sales" in cat or "sales" in raw_text_content.lower() or (doc.invoice_type and "sales" in doc.invoice_type.lower()):
                    note_side = "SALES"
                elif meta_customer_gstin and client_gstin and meta_customer_gstin == client_gstin:
                    note_side = "PURCHASE"
                elif meta_supplier_gstin and client_gstin and meta_supplier_gstin == client_gstin:
                    if cat == "credit_note":
                        note_side = "SALES"
                    else:
                        note_side = "PURCHASE"
                elif doc.customer and not doc.vendor:
                    note_side = "SALES"
                elif doc.vendor and not doc.customer:
                    note_side = "PURCHASE"
                elif cat == "credit_note":
                    note_side = "SALES"
                else:
                    note_side = "PURCHASE"

            if note_side == "SALES":
                is_outward = True
                is_inward = False
            else:
                is_outward = False
                is_inward = True

        elif meta_supplier_gstin and client_gstin and meta_supplier_gstin == client_gstin:
            is_outward = True
        elif meta_customer_gstin and client_gstin and meta_customer_gstin == client_gstin:
            is_inward = True
        else:
            if cat in {"sales_records", "b2c_invoice"} or (doc.invoice_type and "sales" in doc.invoice_type.lower()):
                is_outward = True
            elif cat in {"purchase_records"} or (doc.invoice_type and "purchase" in doc.invoice_type.lower()):
                is_inward = True
            elif cat in {"b2b_invoice", "e_invoice"}:
                is_outward = True

        # ── 3. Validate State Codes & Tax Type Parity ─────────────────────────
        if is_outward:
            sup_gst = meta_supplier_gstin or client_gstin
            rec_gst = meta_customer_gstin or (doc_gstin if doc_gstin != client_gstin else "")
        else:
            sup_gst = meta_supplier_gstin or (doc_gstin if doc_gstin != client_gstin else "")
            rec_gst = meta_customer_gstin or client_gstin

        sup_state = sup_gst[:2] if len(sup_gst) >= 2 and sup_gst[:2].isdigit() else None
        rec_state = rec_gst[:2] if len(rec_gst) >= 2 and rec_gst[:2].isdigit() else None

        if sup_state and rec_state:
            if sup_state == rec_state:
                # Intra-state supply: IGST is prohibited
                if igst > Decimal("0.00"):
                    raise BadRequestException(
                        detail=f"Posting blocked: Tax type does not match state codes. "
                               f"Intra-state supply (Supplier State {sup_state} == Recipient State {rec_state}) "
                               f"cannot have IGST (₹{igst}). Intra-state transactions must use CGST and SGST."
                    )
            else:
                # Inter-state supply: CGST and SGST are prohibited
                if cgst > Decimal("0.00") or sgst > Decimal("0.00"):
                    raise BadRequestException(
                        detail=f"Posting blocked: Tax type does not match state codes. "
                               f"Inter-state supply (Supplier State {sup_state} != Recipient State {rec_state}) "
                               f"cannot have CGST (₹{cgst}) or SGST (₹{sgst}). Inter-state transactions must use IGST."
                    )

        from app.services.accounting_draft_service import parse_flexible_date
        tx_date = parse_flexible_date(doc.invoice_date, doc.uploaded_at) or date.today()
        ref_no = doc.invoice_number or doc.arn or f"DOC-{str(doc.id)[:8]}"

        debit_lines: List[JournalEntryLineCreate] = []
        credit_lines: List[JournalEntryLineCreate] = []
        entry_type = "journal"

        # ── 4. Build Journal Lines with Debits First & GST Accounts Split ─────
        # A. Sales Records & Outward Invoices
        if (cat in {"sales_records", "b2c_invoice"} or (
            cat in {"b2b_invoice", "e_invoice"} and is_outward
        )) and cat not in {"credit_note", "debit_note", "gst_challan"}:
            entry_type = "sales"
            customer_name = doc.customer or "Commercial Customer"
            debtor_acc = get_acc("DEBTORS", "1100", "1010")
            sales_acc = get_acc("SALES", "4010")
            cgst_acc = get_acc("OUTPUT_CGST", "2110")
            sgst_acc = get_acc("OUTPUT_SGST", "2120")
            igst_acc = get_acc("OUTPUT_IGST", "2130")
            cess_acc = get_acc("OUTPUT_CESS", "2140")
            round_acc = acc_map.get("5150") or sales_acc

            if not debtor_acc or not sales_acc:
                raise BadRequestException(detail="Essential sales or debtor accounts missing from client Chart of Accounts")

            # Debits: Debtor (Gross)
            debit_lines.append(
                JournalEntryLineCreate(
                    account_id=debtor_acc.id,
                    debit_amount=gross_amount,
                    credit_amount=Decimal("0.00"),
                    description=f"Receivable from {customer_name}",
                    party_name=customer_name,
                    party_gstin=doc.gstin,
                )
            )

            diff = gross_amount - (taxable_amount + tot_tax)
            if abs(diff) > Decimal("0") and abs(diff) <= Decimal("0.05") and round_acc:
                if diff < Decimal("0"):
                    debit_lines.append(JournalEntryLineCreate(
                        account_id=round_acc.id,
                        debit_amount=abs(diff),
                        credit_amount=Decimal("0.00"),
                        description="Rounding adjustment",
                    ))
                else:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=round_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=diff,
                        description="Rounding adjustment",
                    ))

            # Credits: Output Taxes Split
            if cgst > Decimal("0") and cgst_acc:
                credit_lines.append(JournalEntryLineCreate(
                    account_id=cgst_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=cgst,
                    description="Output CGST on sales",
                    tax_head="cgst",
                ))
            if sgst > Decimal("0") and sgst_acc:
                credit_lines.append(JournalEntryLineCreate(
                    account_id=sgst_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=sgst,
                    description="Output SGST on sales",
                    tax_head="sgst",
                ))
            if igst > Decimal("0") and igst_acc:
                credit_lines.append(JournalEntryLineCreate(
                    account_id=igst_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=igst,
                    description="Output IGST on sales",
                    tax_head="igst",
                ))
            if cess > Decimal("0") and cess_acc:
                credit_lines.append(JournalEntryLineCreate(
                    account_id=cess_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=cess,
                    description="Output Cess on sales",
                    tax_head="cess",
                ))

            credit_lines.append(
                JournalEntryLineCreate(
                    account_id=sales_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=taxable_amount,
                    description="Sales Revenue Turnover",
                )
            )

        # B. Purchase Records & Inward Invoices
        elif (cat == "purchase_records" or (
            cat in {"b2b_invoice", "e_invoice"} and is_inward
        )) and cat not in {"credit_note", "debit_note", "gst_challan"}:
            entry_type = "purchase"
            vendor_name = doc.vendor or "Commercial Vendor"
            creditor_acc = get_acc("CREDITORS", "2010", "1010")
            purchase_acc = get_acc("PURCHASE", "5010")
            cgst_acc = get_acc("INPUT_CGST", "1210")
            sgst_acc = get_acc("INPUT_SGST", "1220")
            igst_acc = get_acc("INPUT_IGST", "1230")
            cess_acc = get_acc("INPUT_CESS", "1240")
            round_acc = acc_map.get("5150") or purchase_acc

            if not creditor_acc or not purchase_acc:
                raise BadRequestException(detail="Essential purchase or creditor accounts missing from client Chart of Accounts")

            # Debits: Input Taxes Split + Purchase Expense
            if cgst > Decimal("0") and cgst_acc:
                debit_lines.append(JournalEntryLineCreate(
                    account_id=cgst_acc.id,
                    debit_amount=cgst,
                    credit_amount=Decimal("0.00"),
                    description="Input CGST (ITC Claimable)",
                    tax_head="cgst",
                ))
            if sgst > Decimal("0") and sgst_acc:
                debit_lines.append(JournalEntryLineCreate(
                    account_id=sgst_acc.id,
                    debit_amount=sgst,
                    credit_amount=Decimal("0.00"),
                    description="Input SGST (ITC Claimable)",
                    tax_head="sgst",
                ))
            if igst > Decimal("0") and igst_acc:
                debit_lines.append(JournalEntryLineCreate(
                    account_id=igst_acc.id,
                    debit_amount=igst,
                    credit_amount=Decimal("0.00"),
                    description="Input IGST (ITC Claimable)",
                    tax_head="igst",
                ))
            if cess > Decimal("0") and cess_acc:
                debit_lines.append(JournalEntryLineCreate(
                    account_id=cess_acc.id,
                    debit_amount=cess,
                    credit_amount=Decimal("0.00"),
                    description="Input Cess (ITC Claimable)",
                    tax_head="cess",
                ))

            debit_lines.append(
                JournalEntryLineCreate(
                    account_id=purchase_acc.id,
                    debit_amount=taxable_amount,
                    credit_amount=Decimal("0.00"),
                    description="Direct Purchase Consideration",
                )
            )

            diff = gross_amount - (taxable_amount + tot_tax)
            if abs(diff) > Decimal("0") and abs(diff) <= Decimal("0.05") and round_acc:
                if diff > Decimal("0"):
                    debit_lines.append(JournalEntryLineCreate(
                        account_id=round_acc.id,
                        debit_amount=diff,
                        credit_amount=Decimal("0.00"),
                        description="Rounding adjustment",
                    ))
                else:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=round_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=abs(diff),
                        description="Rounding adjustment",
                    ))

            # Credits: Creditor (Gross)
            credit_lines.append(
                JournalEntryLineCreate(
                    account_id=creditor_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=gross_amount,
                    description=f"Payable to {vendor_name}",
                    party_name=vendor_name,
                    party_gstin=doc.gstin,
                )
            )

        # C. Credit Notes (Sales Return or Purchase Rebate)
        elif cat == "credit_note":
            entry_type = "journal"
            if is_outward:
                customer_name = doc.customer or "Customer"
                debtor_acc = get_acc("DEBTORS", "1100", "1010")
                sales_return_acc = get_acc("SALES_RETURN", "4030", "4020", "4010")
                cgst_acc = get_acc("OUTPUT_CGST", "2110")
                sgst_acc = get_acc("OUTPUT_SGST", "2120")
                igst_acc = get_acc("OUTPUT_IGST", "2130")
                cess_acc = get_acc("OUTPUT_CESS", "2140")
                round_acc = acc_map.get("5150") or sales_return_acc

                if not debtor_acc or not sales_return_acc:
                    raise BadRequestException(detail="Essential sales return or debtor accounts missing")

                # Debits: Sales Return + Output Taxes Reversals
                debit_lines.append(JournalEntryLineCreate(
                    account_id=sales_return_acc.id,
                    debit_amount=taxable_amount,
                    credit_amount=Decimal("0.00"),
                    description=f"Sales Return adjustment against {customer_name}",
                ))
                if cgst > Decimal("0") and cgst_acc:
                    debit_lines.append(JournalEntryLineCreate(
                        account_id=cgst_acc.id,
                        debit_amount=cgst,
                        credit_amount=Decimal("0.00"),
                        description="Output CGST Reversal (Credit Note)",
                        tax_head="cgst",
                    ))
                if sgst > Decimal("0") and sgst_acc:
                    debit_lines.append(JournalEntryLineCreate(
                        account_id=sgst_acc.id,
                        debit_amount=sgst,
                        credit_amount=Decimal("0.00"),
                        description="Output SGST Reversal (Credit Note)",
                        tax_head="sgst",
                    ))
                if igst > Decimal("0") and igst_acc:
                    debit_lines.append(JournalEntryLineCreate(
                        account_id=igst_acc.id,
                        debit_amount=igst,
                        credit_amount=Decimal("0.00"),
                        description="Output IGST Reversal (Credit Note)",
                        tax_head="igst",
                    ))
                if cess > Decimal("0") and cess_acc:
                    debit_lines.append(JournalEntryLineCreate(
                        account_id=cess_acc.id,
                        debit_amount=cess,
                        credit_amount=Decimal("0.00"),
                        description="Output Cess Reversal (Credit Note)",
                        tax_head="cess",
                    ))

                diff = gross_amount - (taxable_amount + tot_tax)
                if abs(diff) > Decimal("0") and abs(diff) <= Decimal("0.05") and round_acc:
                    if diff < Decimal("0"):
                        debit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=abs(diff),
                            credit_amount=Decimal("0.00"),
                            description="Rounding adjustment",
                        ))
                    else:
                        credit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=Decimal("0.00"),
                            credit_amount=diff,
                            description="Rounding adjustment",
                        ))

                # Credits: Debtor Credited (Gross)
                credit_lines.append(JournalEntryLineCreate(
                    account_id=debtor_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=gross_amount,
                    description=f"Credit Note credit to {customer_name}",
                    party_name=customer_name,
                    party_gstin=doc.gstin,
                ))
            else:
                vendor_name = doc.vendor or "Vendor"
                creditor_acc = get_acc("CREDITORS", "2010", "1010")
                purchase_return_acc = get_acc("PURCHASE_RETURN", "5020", "5010")
                cgst_acc = get_acc("INPUT_CGST", "1210")
                sgst_acc = get_acc("INPUT_SGST", "1220")
                igst_acc = get_acc("INPUT_IGST", "1230")
                cess_acc = get_acc("INPUT_CESS", "1240")
                round_acc = acc_map.get("5150") or purchase_return_acc

                if not creditor_acc or not purchase_return_acc:
                    raise BadRequestException(detail="Essential purchase return or creditor accounts missing")

                # Debits: Creditor Debited (Gross)
                debit_lines.append(JournalEntryLineCreate(
                    account_id=creditor_acc.id,
                    debit_amount=gross_amount,
                    credit_amount=Decimal("0.00"),
                    description=f"Credit Note received from {vendor_name}",
                    party_name=vendor_name,
                    party_gstin=doc.gstin,
                ))

                diff = gross_amount - (taxable_amount + tot_tax)
                if abs(diff) > Decimal("0") and abs(diff) <= Decimal("0.05") and round_acc:
                    if diff > Decimal("0"):
                        debit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=diff,
                            credit_amount=Decimal("0.00"),
                            description="Rounding adjustment",
                        ))
                    else:
                        credit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=Decimal("0.00"),
                            credit_amount=abs(diff),
                            description="Rounding adjustment",
                        ))

                # Credits: Purchase Return + Input Taxes Reversals
                credit_lines.append(JournalEntryLineCreate(
                    account_id=purchase_return_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=taxable_amount,
                    description=f"Purchase Return/Discount from {vendor_name}",
                ))
                if cgst > Decimal("0") and cgst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=cgst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=cgst,
                        description="Input CGST Reversal (Credit Note)",
                        tax_head="cgst",
                    ))
                if sgst > Decimal("0") and sgst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=sgst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=sgst,
                        description="Input SGST Reversal (Credit Note)",
                        tax_head="sgst",
                    ))
                if igst > Decimal("0") and igst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=igst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=igst,
                        description="Input IGST Reversal (Credit Note)",
                        tax_head="igst",
                    ))
                if cess > Decimal("0") and cess_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=cess_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=cess,
                        description="Input Cess Reversal (Credit Note)",
                        tax_head="cess",
                    ))

        # D. Debit Notes (Purchase Return or Supplementary Outward Sales)
        elif cat == "debit_note":
            entry_type = "journal"
            if is_inward:
                vendor_name = doc.vendor or "Vendor"
                creditor_acc = get_acc("CREDITORS", "2010", "1010")
                purchase_return_acc = get_acc("PURCHASE_RETURN", "5020", "5010")
                cgst_acc = get_acc("INPUT_CGST", "1210")
                sgst_acc = get_acc("INPUT_SGST", "1220")
                igst_acc = get_acc("INPUT_IGST", "1230")
                cess_acc = get_acc("INPUT_CESS", "1240")
                round_acc = acc_map.get("5150") or purchase_return_acc

                if not creditor_acc or not purchase_return_acc:
                    raise BadRequestException(detail="Essential purchase return or creditor accounts missing")

                # Debits: Creditor Debited (Gross)
                debit_lines.append(JournalEntryLineCreate(
                    account_id=creditor_acc.id,
                    debit_amount=gross_amount,
                    credit_amount=Decimal("0.00"),
                    description=f"Debit Note debit to {vendor_name}",
                    party_name=vendor_name,
                    party_gstin=doc.gstin,
                ))

                diff = gross_amount - (taxable_amount + tot_tax)
                if abs(diff) > Decimal("0") and abs(diff) <= Decimal("0.05") and round_acc:
                    if diff > Decimal("0"):
                        debit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=diff,
                            credit_amount=Decimal("0.00"),
                            description="Rounding adjustment",
                        ))
                    else:
                        credit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=Decimal("0.00"),
                            credit_amount=abs(diff),
                            description="Rounding adjustment",
                        ))

                # Credits: Purchase Return + Input Taxes Reversals
                credit_lines.append(JournalEntryLineCreate(
                    account_id=purchase_return_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=taxable_amount,
                    description=f"Purchase Return adjustment from {vendor_name}",
                ))
                if cgst > Decimal("0") and cgst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=cgst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=cgst,
                        description="Input CGST Reversal (Debit Note)",
                        tax_head="cgst",
                    ))
                if sgst > Decimal("0") and sgst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=sgst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=sgst,
                        description="Input SGST Reversal (Debit Note)",
                        tax_head="sgst",
                    ))
                if igst > Decimal("0") and igst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=igst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=igst,
                        description="Input IGST Reversal (Debit Note)",
                        tax_head="igst",
                    ))
                if cess > Decimal("0") and cess_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=cess_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=cess,
                        description="Input Cess Reversal (Debit Note)",
                        tax_head="cess",
                    ))
            else:
                customer_name = doc.customer or "Customer"
                debtor_acc = get_acc("DEBTORS", "1100", "1010")
                other_sales_acc = get_acc("OTHER_INCOME", "4030", "4010")
                cgst_acc = get_acc("OUTPUT_CGST", "2110")
                sgst_acc = get_acc("OUTPUT_SGST", "2120")
                igst_acc = get_acc("OUTPUT_IGST", "2130")
                cess_acc = get_acc("OUTPUT_CESS", "2140")
                round_acc = acc_map.get("5150") or other_sales_acc

                if not debtor_acc or not other_sales_acc:
                    raise BadRequestException(detail="Essential sales or debtor accounts missing")

                # Debits: Debtor Debited (Gross)
                debit_lines.append(JournalEntryLineCreate(
                    account_id=debtor_acc.id,
                    debit_amount=gross_amount,
                    credit_amount=Decimal("0.00"),
                    description=f"Debit Note (Supplementary) against {customer_name}",
                    party_name=customer_name,
                    party_gstin=doc.gstin,
                ))

                diff = gross_amount - (taxable_amount + tot_tax)
                if abs(diff) > Decimal("0") and abs(diff) <= Decimal("0.05") and round_acc:
                    if diff < Decimal("0"):
                        debit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=abs(diff),
                            credit_amount=Decimal("0.00"),
                            description="Rounding adjustment",
                        ))
                    else:
                        credit_lines.append(JournalEntryLineCreate(
                            account_id=round_acc.id,
                            debit_amount=Decimal("0.00"),
                            credit_amount=diff,
                            description="Rounding adjustment",
                        ))

                # Credits: Other Sales/Income + Output Taxes
                credit_lines.append(JournalEntryLineCreate(
                    account_id=other_sales_acc.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=taxable_amount,
                    description=f"Supplementary Sales Revenue from {customer_name}",
                ))
                if cgst > Decimal("0") and cgst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=cgst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=cgst,
                        description="Output CGST on Debit Note",
                        tax_head="cgst",
                    ))
                if sgst > Decimal("0") and sgst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=sgst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=sgst,
                        description="Output SGST on Debit Note",
                        tax_head="sgst",
                    ))
                if igst > Decimal("0") and igst_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=igst_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=igst,
                        description="Output IGST on Debit Note",
                        tax_head="igst",
                    ))
                if cess > Decimal("0") and cess_acc:
                    credit_lines.append(JournalEntryLineCreate(
                        account_id=cess_acc.id,
                        debit_amount=Decimal("0.00"),
                        credit_amount=cess,
                        description="Output Cess on Debit Note",
                        tax_head="cess",
                    ))

        # E. GST Challans
        elif cat == "gst_challan":
            entry_type = "payment"
            gst_clearing_acc = acc_map.get("2150") or acc_map.get("2200")
            bank_acc = acc_map.get("1020") or acc_map.get("1010")

            if not gst_clearing_acc or not bank_acc:
                raise BadRequestException(detail="Essential tax clearing or bank accounts missing")

            debit_lines.append(JournalEntryLineCreate(
                account_id=gst_clearing_acc.id,
                debit_amount=gross_amount,
                credit_amount=Decimal("0.00"),
                description=f"GST Tax Liability Settlement (Ref: {ref_no})",
            ))
            credit_lines.append(JournalEntryLineCreate(
                account_id=bank_acc.id,
                debit_amount=Decimal("0.00"),
                credit_amount=gross_amount,
                description=f"Statutory payment via Banking Channel (Ref: {ref_no})",
            ))

        else:
            raise BadRequestException(detail=f"Category '{cat}' does not support automatic journal posting")

        lines = debit_lines + credit_lines

        narration = f"{entry_type.upper()} Voucher | Ref: {ref_no} | Gross: ₹{gross_amount} | Linked Document: {doc.id}"

        return JournalEntryCreate(
            client_id=doc.client_id,
            document_id=doc.id,
            entry_date=tx_date,
            entry_type=entry_type,
            narration=narration,
            reference_number=ref_no,
            lines=lines,
        )
