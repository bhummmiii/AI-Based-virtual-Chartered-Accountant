"""
Accounting Draft Service — Bridge between Verified Documents and Accounting Records.

Ensures:
1. Only verified documents generate accounting drafts.
2. Informational documents are strictly excluded from financial posting.
3. Category-to-voucher transaction mapping for sales, purchases, credit/debit notes, tax payments.
4. Validation of amounts, dates, parties, and categories.
5. Idempotent draft creation (prevents duplicate drafts; updates existing drafts on document edits).
6. Explicit posting workflow: Drafts remain unposted until explicitly confirmed by the CA.
7. Audit-friendly source document linking.
"""

import re
import uuid
import logging
from typing import Optional, List, Tuple, Dict, Any
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounting_record import AccountingRecord
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry
from app.models.client import Client
from app.models.user import User
from app.services.journal_entry_service import JournalEntryService
from app.services.accounting_mapping_service import AccountingMappingService
from app.schemas.journal_entry import (
    JournalEntryCreate,
    JournalEntryLineCreate,
    JournalEntryResponse,
)
from app.schemas.accounting import (
    AccountingValidationResult,
    DraftGenerateResponse,
    DraftPostResponse,
    DraftBulkPostResponse,
    AccountingRecordResponse,
)
from app.core.exceptions import ForbiddenException, BadRequestException


logger = logging.getLogger(__name__)

# Categories that represent financial transactions
FINANCIAL_CATEGORIES = {
    "sales_records",
    "purchase_records",
    "b2b_invoice",
    "b2c_invoice",
    "e_invoice",
    "credit_note",
    "debit_note",
    "gst_challan",
}

# Informational categories that MUST NOT be posted to the ledger
INFORMATIONAL_CATEGORIES = {
    "document_list",
    "gst_notice",
    "hsn_sac",
    "gst_return",
    "e_way_bill",
}


def parse_flexible_date(date_val: Any, fallback: Optional[datetime] = None) -> Optional[date]:
    """Safely parse various date string representations into a datetime.date object."""
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    if not date_val or not isinstance(date_val, str) or not date_val.strip():
        return fallback.date() if fallback else None

    cleaned = date_val.strip()
    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%d-%b-%Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%m/%d/%Y",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    # ISO regex matching: YYYY-MM-DD
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", cleaned)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # DD-MM-YYYY regex matching
    match_dmy = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", cleaned)
    if match_dmy:
        try:
            return date(int(match_dmy.group(3)), int(match_dmy.group(2)), int(match_dmy.group(1)))
        except ValueError:
            pass

    return fallback.date() if fallback else None


class AccountingDraftService:
    """Core service for managing the Document -> Accounting Draft lifecycle."""

    @staticmethod
    def validate_document(doc: UploadedDocument) -> AccountingValidationResult:
        """
        Validate whether a verified document is eligible to generate an accounting draft.
        Returns an AccountingValidationResult with clear validation details.
        """
        warnings: List[str] = []

        # 1. Informational documents check
        if doc.document_category in INFORMATIONAL_CATEGORIES:
            return AccountingValidationResult(
                eligible=False,
                status="informational_skipped",
                reason=(
                    f"Category '{doc.document_category}' is informational. "
                    "Informational documents are excluded from financial ledger posting."
                ),
                document_id=doc.id,
                document_category=doc.document_category,
                warnings=[],
            )

        # 2. Check if category is supported
        if doc.document_category not in FINANCIAL_CATEGORIES:
            return AccountingValidationResult(
                eligible=False,
                status="validation_error",
                reason=f"Unsupported document category for accounting: '{doc.document_category}'",
                document_id=doc.id,
                document_category=doc.document_category,
                warnings=[],
            )

        # 3. Check verification status
        if doc.status != "verified":
            return AccountingValidationResult(
                eligible=False,
                status="unverified",
                reason=(
                    f"Document must be verified before preparing accounting drafts. "
                    f"Current status is '{doc.status}'."
                ),
                document_id=doc.id,
                document_category=doc.document_category,
                warnings=[],
            )

        # 4. Amount validation
        if doc.amount is None or doc.amount <= Decimal("0"):
            return AccountingValidationResult(
                eligible=False,
                status="validation_error",
                reason="Document amount must be present and greater than 0.",
                document_id=doc.id,
                document_category=doc.document_category,
                warnings=[],
            )

        # 5. Party validation
        party_name = doc.customer if doc.document_category in {"sales_records", "b2c_invoice", "credit_note"} else doc.vendor
        if not party_name:
            # Fallback check other party column
            party_name = doc.vendor if doc.customer is None else doc.customer

        if not party_name and doc.document_category != "gst_challan":
            return AccountingValidationResult(
                eligible=False,
                status="validation_error",
                reason=(
                    f"Party name (vendor/customer) is required for {doc.document_category}. "
                    "Please edit and verify the document before preparing accounting drafts."
                ),
                document_id=doc.id,
                document_category=doc.document_category,
                warnings=[],
            )

        # 6. Date validation
        parsed_date = parse_flexible_date(doc.invoice_date, doc.uploaded_at)
        if not parsed_date:
            return AccountingValidationResult(
                eligible=False,
                status="validation_error",
                reason="Unable to determine transaction date from invoice date or upload date.",
                document_id=doc.id,
                document_category=doc.document_category,
                warnings=[],
            )

        if not doc.invoice_date:
            warnings.append("Invoice date was missing; used upload timestamp as transaction date.")

        return AccountingValidationResult(
            eligible=True,
            status="valid",
            reason=None,
            document_id=doc.id,
            document_category=doc.document_category,
            warnings=warnings,
        )

    @classmethod
    def map_document_to_record_fields(cls, doc: UploadedDocument) -> Dict[str, Any]:
        """
        Map verified document fields to AccountingRecord transaction attributes.
        Derives voucher type, category, debit/credit orientation, reference, and audit description.
        """
        category = doc.document_category
        amount = Decimal(str(doc.amount))
        tx_date = parse_flexible_date(doc.invoice_date, doc.uploaded_at) or date.today()

        debit = Decimal("0.00")
        credit = Decimal("0.00")
        voucher_type = "journal"
        record_category = "misc"
        party_label = "Party"

        if category in {"sales_records", "b2c_invoice"}:
            voucher_type = "sales"
            record_category = "sales"
            party_label = doc.customer or "Customer"
            credit = amount  # Sales Revenue credited

        elif category == "purchase_records":
            voucher_type = "purchase"
            record_category = "purchase"
            party_label = doc.vendor or "Vendor"
            debit = amount   # Purchase Expense debited

        elif category in {"b2b_invoice", "e_invoice"}:
            # Default to sales if customer is populated or invoice_type indicates sales
            if doc.invoice_type and "purchase" in doc.invoice_type.lower():
                voucher_type = "purchase"
                record_category = "purchase"
                party_label = doc.vendor or "Vendor"
                debit = amount
            else:
                voucher_type = "sales"
                record_category = "sales"
                party_label = doc.customer or doc.vendor or "Customer"
                credit = amount

        elif category == "credit_note":
            voucher_type = "journal"
            record_category = "credit_note"
            party_label = doc.customer or "Customer"
            debit = amount  # Sales Return debited

        elif category == "debit_note":
            voucher_type = "journal"
            record_category = "debit_note"
            party_label = doc.vendor or "Vendor"
            credit = amount  # Purchase Return credited

        elif category == "gst_challan":
            voucher_type = "payment"
            record_category = "tax"
            party_label = "GST Tax Authority (Government Treasury)"
            debit = amount  # Tax Liability settlement debited

        # Build detailed audit trail in description
        taxable_str = f"Taxable: ₹{doc.taxable_amount}" if doc.taxable_amount is not None else ""
        taxes = []
        if doc.cgst:
            taxes.append(f"CGST: ₹{doc.cgst}")
        if doc.sgst:
            taxes.append(f"SGST: ₹{doc.sgst}")
        if doc.igst:
            taxes.append(f"IGST: ₹{doc.igst}")
        if doc.cess:
            taxes.append(f"Cess: ₹{doc.cess}")
        tax_str = f" | {', '.join(taxes)}" if taxes else ""
        taxable_part = f" | {taxable_str}" if taxable_str else ""

        ref_no = doc.invoice_number or doc.arn or doc.notice_number or f"DOC-{str(doc.id)[:8]}"
        description = (
            f"Ref: {ref_no} | Party: {party_label} | "
            f"Total: ₹{amount}{taxable_part}{tax_str}"
        )

        return {
            "client_id": doc.client_id,
            "document_id": doc.id,
            "transaction_date": tx_date,
            "voucher_type": voucher_type,
            "category": record_category,
            "debit": debit,
            "credit": credit,
            "reference_number": ref_no,
            "description": description,
            "status": "draft",
        }

    @classmethod
    def generate_or_update_draft(
        cls,
        db: Session,
        document_id: uuid.UUID,
    ) -> DraftGenerateResponse:
        """
        Generate or update an accounting draft for a verified document.
        Idempotent:
        - If an unposted draft already exists for this document, updates it in place.
        - If the document was already posted to the ledger, rejects re-drafting.
        - If informational, skips with informative status.
        """
        doc = db.query(UploadedDocument).filter(UploadedDocument.id == document_id).first()
        if not doc:
            return DraftGenerateResponse(
                status="error",
                message=f"Document with ID {document_id} not found.",
                record=None,
                validation=None,
            )

        # 1. Validate document
        val_result = cls.validate_document(doc)
        if not val_result.eligible:
            return DraftGenerateResponse(
                status="skipped" if val_result.status == "informational_skipped" else "error",
                message=val_result.reason or "Document validation failed.",
                record=None,
                validation=val_result,
            )

        # 2. Check duplicate / existing accounting records for this document
        existing = (
            db.query(AccountingRecord)
            .filter(AccountingRecord.document_id == document_id)
            .first()
        )

        if existing and existing.status == "posted":
            val_result = AccountingValidationResult(
                eligible=False,
                status="already_posted",
                reason=(
                    f"Document has already been posted to the accounting ledger (Record ID: {existing.id}). "
                    "Draft cannot be regenerated for an already posted entry."
                ),
                document_id=doc.id,
                document_category=doc.document_category,
            )
            return DraftGenerateResponse(
                status="error",
                message=val_result.reason,
                record=AccountingRecordResponse.model_validate(existing),
                validation=val_result,
            )

        # 2b. Check distinct commercial transaction for B2B/B2C invoices (prevent duplicate postings of same reference)
        ref_no = doc.invoice_number
        if ref_no and doc.document_category in {"b2b_invoice", "b2c_invoice"}:
            duplicate_ref = (
                db.query(AccountingRecord)
                .filter(
                    AccountingRecord.client_id == doc.client_id,
                    AccountingRecord.reference_number == ref_no,
                    AccountingRecord.document_id != doc.id,
                    AccountingRecord.status == "posted",
                )
                .first()
            )
            if duplicate_ref:
                val_result = AccountingValidationResult(
                    eligible=False,
                    status="duplicate_invoice",
                    reason=(
                        f"Duplicate commercial transaction detected: An accounting record with reference '{ref_no}' "
                        f"has already been posted to the ledger for this client (Record ID: {duplicate_ref.id})."
                    ),
                    document_id=doc.id,
                    document_category=doc.document_category,
                )
                return DraftGenerateResponse(
                    status="error",
                    message=val_result.reason,
                    record=AccountingRecordResponse.model_validate(duplicate_ref),
                    validation=val_result,
                )

        # 3. Map fields
        fields = cls.map_document_to_record_fields(doc)

        if existing and existing.status == "draft":
            # Update existing draft in-place
            existing.transaction_date = fields["transaction_date"]
            existing.voucher_type = fields["voucher_type"]
            existing.category = fields["category"]
            existing.debit = fields["debit"]
            existing.credit = fields["credit"]
            existing.reference_number = fields["reference_number"]
            existing.description = fields["description"]
            db.commit()
            db.refresh(existing)

            logger.info("Updated existing accounting draft %s for document %s", existing.id, doc.id)
            return DraftGenerateResponse(
                status="updated",
                message=f"Accounting draft updated successfully for document {doc.invoice_number or doc.id}.",
                record=AccountingRecordResponse.model_validate(existing),
                validation=val_result,
            )

        # 4. Create new draft
        new_draft = AccountingRecord(**fields)
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)

        logger.info("Created new accounting draft %s for document %s", new_draft.id, doc.id)
        return DraftGenerateResponse(
            status="created",
            message=f"Accounting draft created successfully for document {doc.invoice_number or doc.id}.",
            record=AccountingRecordResponse.model_validate(new_draft),
            validation=val_result,
        )

    @staticmethod
    def get_drafts(
        db: Session,
        client_id: Optional[uuid.UUID] = None,
        document_id: Optional[uuid.UUID] = None,
        status: Optional[str] = "draft",
    ) -> List[AccountingRecord]:
        """Fetch accounting records filtered by client, document, and status."""
        query = db.query(AccountingRecord)
        if client_id:
            query = query.filter(AccountingRecord.client_id == client_id)
        if document_id:
            query = query.filter(AccountingRecord.document_id == document_id)
        if status and status.lower() not in {"all", "*", ""}:
            query = query.filter(AccountingRecord.status == status)
        return query.order_by(AccountingRecord.transaction_date.desc()).all()

    @staticmethod
    def get_draft_by_id(db: Session, draft_id: uuid.UUID) -> Optional[AccountingRecord]:
        """Retrieve a specific accounting record by ID."""
        return db.query(AccountingRecord).filter(AccountingRecord.id == draft_id).first()

    @classmethod
    def post_draft_to_ledger(
        cls,
        db: Session,
        draft_id: uuid.UUID,
        user: Optional[User] = None,
    ) -> DraftPostResponse:
        """
        Explicitly post a draft record to the ledger.
        Atomically updates AccountingRecord status to 'posted' AND creates a persistent
        balanced JournalEntry + JournalEntryLines linked to Chart of Accounts.
        """
        # 1. Acquire row-level lock where supported
        query = db.query(AccountingRecord).filter(AccountingRecord.id == draft_id)
        if db.bind and hasattr(db.bind, "dialect") and db.bind.dialect.name == "postgresql":
            record = query.with_for_update().first()
        else:
            record = query.first()

        if not record:
            return DraftPostResponse(
                success=False,
                message=f"Draft record with ID {draft_id} not found.",
                record=None,
                journal_entry=None,
            )

        # 2. Authorization verification
        if user:
            client = db.query(Client).filter(Client.id == record.client_id).first()
            if client and user.role != "admin" and client.user_id is not None and client.user_id != user.id:
                raise ForbiddenException(detail="You are not authorized to post accounting records for this client")

        # 3. Idempotent check: if already posted, return existing records
        if record.status == "posted":
            je = db.query(JournalEntry).filter(JournalEntry.accounting_record_id == record.id).first()
            je_resp = JournalEntryResponse.model_validate(je) if je else None
            return DraftPostResponse(
                success=True,
                message=f"Record {draft_id} is already posted to the ledger.",
                record=AccountingRecordResponse.model_validate(record),
                journal_entry=je_resp,
            )

        # 4. Period lockout check: prevent posting into closed fiscal periods
        from app.services.trial_balance_service import TrialBalanceService
        is_closed, closed_pname = TrialBalanceService.is_period_closed_for_date(db, record.client_id, record.transaction_date)
        if is_closed:
            return DraftPostResponse(
                success=False,
                message=f"Accounting period '{closed_pname}' is closed. Posting to {record.transaction_date} is prohibited.",
                record=None,
                journal_entry=None,
            )

        # 5. Atomic dual-layer write
        je_obj = None
        try:
            with db.begin_nested():
                # A. Try mapping verified source document
                audit_user = user or User(id=uuid.uuid4(), role="admin", full_name="FinLedger System", email="system@finledger.local")
                if record.document_id:
                    doc = db.query(UploadedDocument).filter(UploadedDocument.id == record.document_id).first()
                    if not doc:
                        raise NotFoundException(detail=f"Source document {record.document_id} not found")
                    if getattr(doc, "status", "") in ("needs_review", "blocked") or getattr(doc, "invoice_type", "") == "needs_review":
                        raise BadRequestException(
                            detail=f"Posting blocked: Source document #{doc.invoice_number or doc.id} has status '{doc.status}' and requires CA review before posting."
                        )
                    je_payload = AccountingMappingService.map_document_to_journal_entry(db, doc, audit_user)
                    je_payload.accounting_record_id = record.id
                    je_obj = JournalEntryService.create_journal_entry(
                        db=db,
                        client_id=record.client_id,
                        payload=je_payload,
                        user=audit_user,
                        auto_commit=False,
                    )

                # B. If no document or mapping didn't run, create a balanced journal entry from flat record
                if not je_obj and (record.debit > Decimal("0") or record.credit > Decimal("0")):
                    acc_map = AccountingMappingService.get_or_init_client_accounts(db, record.client_id, audit_user)
                    amount_val = record.debit if record.debit > Decimal("0") else record.credit
                    is_debit = record.debit > Decimal("0")

                    if record.voucher_type == "sales":
                        dr_acc = acc_map.get("1100") or acc_map.get("1010")
                        cr_acc = acc_map.get("4010")
                    elif record.voucher_type == "purchase":
                        dr_acc = acc_map.get("5010")
                        cr_acc = acc_map.get("2010") or acc_map.get("1010")
                    elif record.voucher_type == "payment":
                        dr_acc = acc_map.get("2150") or acc_map.get("2010")
                        cr_acc = acc_map.get("1020") or acc_map.get("1010")
                    else:
                        dr_acc = acc_map.get("5010") if is_debit else acc_map.get("1020")
                        cr_acc = acc_map.get("1020") if is_debit else acc_map.get("4010")

                    if dr_acc and cr_acc:
                        je_lines = [
                            JournalEntryLineCreate(
                                account_id=dr_acc.id,
                                debit_amount=amount_val,
                                credit_amount=Decimal("0.00"),
                                description=record.description or "Debit posting leg",
                            ),
                            JournalEntryLineCreate(
                                account_id=cr_acc.id,
                                debit_amount=Decimal("0.00"),
                                credit_amount=amount_val,
                                description=record.description or "Credit posting leg",
                            ),
                        ]
                        je_payload = JournalEntryCreate(
                            client_id=record.client_id,
                            accounting_record_id=record.id,
                            document_id=record.document_id,
                            entry_date=record.transaction_date,
                            entry_type=record.voucher_type,
                            narration=record.description,
                            reference_number=record.reference_number,
                            lines=je_lines,
                        )
                        je_obj = JournalEntryService.create_journal_entry(
                            db=db,
                            client_id=record.client_id,
                            payload=je_payload,
                            user=audit_user,
                            auto_commit=False,
                        )

                # C. Update AccountingRecord status and audit note
                record.status = "posted"
                posted_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                if record.description:
                    clean_desc = re.sub(r"^\[.*?DRAFT\]\s*", "", record.description)
                    if "Posted:" not in clean_desc:
                        record.description = f"{clean_desc} | Posted: {posted_ts}"
                    else:
                        record.description = clean_desc
                else:
                    record.description = f"Posted: {posted_ts}"

            db.commit()
            db.refresh(record)
            if je_obj:
                db.refresh(je_obj)

        except Exception as e:
            db.rollback()
            logger.exception("Failed to post draft %s to ledger: %s", draft_id, e)
            return DraftPostResponse(
                success=False,
                message=f"Failed to post draft to ledger: {str(e)}",
                record=None,
                journal_entry=None,
            )

        logger.info(
            "Draft %s explicitly posted to ledger as record %s (Journal Entry: %s)",
            draft_id, record.id, je_obj.entry_number if je_obj else "None"
        )
        return DraftPostResponse(
            success=True,
            message="Draft successfully posted to accounting ledger.",
            record=AccountingRecordResponse.model_validate(record),
            journal_entry=JournalEntryResponse.model_validate(je_obj) if je_obj else None,
        )

    @classmethod
    def bulk_post_drafts(
        cls,
        db: Session,
        draft_ids: List[uuid.UUID],
        user: Optional[User] = None,
    ) -> DraftBulkPostResponse:
        """Explicitly post multiple approved drafts in batch."""
        posted_ids: List[uuid.UUID] = []
        errors: List[str] = []

        for draft_id in draft_ids:
            res = cls.post_draft_to_ledger(db, draft_id, user=user)
            if res.success and res.record:
                posted_ids.append(res.record.id)
            else:
                errors.append(f"{draft_id}: {res.message}")

        return DraftBulkPostResponse(
            total_requested=len(draft_ids),
            posted_count=len(posted_ids),
            failed_count=len(errors),
            posted_ids=posted_ids,
            errors=errors,
        )

    @staticmethod
    def delete_draft(db: Session, draft_id: uuid.UUID) -> Tuple[bool, str]:
        """
        Safely delete an unposted draft.
        Posted ledger records cannot be deleted through this endpoint.
        """
        record = db.query(AccountingRecord).filter(AccountingRecord.id == draft_id).first()
        if not record:
            return False, f"Draft with ID {draft_id} not found."

        if record.status == "posted":
            return False, "Cannot delete a posted accounting record. Only unposted drafts may be deleted."

        db.delete(record)
        db.commit()
        return True, "Draft successfully deleted."
