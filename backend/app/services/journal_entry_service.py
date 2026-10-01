"""
Journal Entry Service — Core engine for Double-Entry Journal Postings.
Adheres to ICAI accounting standards and ensures:
1. Strict mathematical balance: Total Debit == Total Credit.
2. Complete client account isolation: Cannot reference another client's accounts.
3. Active account validation: Cannot post to deactivated accounts.
4. Auto-sequenced voucher numbering per client.
5. Immutability: Posted entries cannot be updated or deleted.
6. Audit-compliant reversal mechanism.
"""

import uuid
import logging
from typing import Optional, List, Dict, Tuple
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.chart_of_accounts import ChartOfAccounts
from app.models.accounting_period import AccountingPeriod
from app.models.client import Client
from app.models.user import User
from app.schemas.journal_entry import JournalEntryCreate
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ForbiddenException,
    BadRequestException,
)

logger = logging.getLogger(__name__)


class JournalEntryService:

    @staticmethod
    def verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
        """Verify that client exists and authenticated user has authorization."""
        client = db.query(Client).filter(Client.id == client_id, Client.status != "deleted").first()
        if not client:
            raise NotFoundException(detail=f"Client {client_id} not found")

        if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
            raise ForbiddenException(detail="You are not authorized to access accounting records for this client")

        return client

    @classmethod
    def generate_next_entry_number(cls, db: Session, client_id: uuid.UUID, entry_type: str) -> str:
        """
        Generate sequential voucher entry number per client and type.
        Prefix format: SV (Sales), PV (Purchase), PMT (Payment), RCT (Receipt), JV (Journal), CN (Contra).
        """
        type_prefix_map = {
            "sales": "SV",
            "purchase": "PV",
            "payment": "PMT",
            "receipt": "RCT",
            "contra": "CN",
            "journal": "JV",
            "reversal": "REV",
        }
        prefix = type_prefix_map.get(entry_type.lower(), "JV")
        year_str = str(date.today().year)

        count = (
            db.query(func.count(JournalEntry.id))
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.entry_type == entry_type.lower(),
            )
            .scalar()
            or 0
        )
        seq = count + 1
        candidate = f"{prefix}-{year_str}-{seq:04d}"
        while db.query(JournalEntry).filter(
            JournalEntry.client_id == client_id,
            JournalEntry.entry_number == candidate,
        ).first():
            seq += 1
            candidate = f"{prefix}-{year_str}-{seq:04d}"
        return candidate

    @classmethod
    def create_journal_entry(
        cls,
        db: Session,
        client_id: uuid.UUID,
        payload: JournalEntryCreate,
        user: User,
        auto_commit: bool = True,
    ) -> JournalEntry:

        """
        Create and persist a balanced double-entry journal entry with lines.
        Enforces:
        - Client isolation: all accounts must belong to client_id.
        - Active account validation: no inactive accounts.
        - Mathematical balance: Total Debit == Total Credit.
        - Duplicate prevention: cannot create duplicate journal for same accounting_record_id.
        """
        cls.verify_client_access(db, client_id, user)

        if payload.client_id != client_id:
            raise BadRequestException(detail="Payload client_id does not match the route client_id")

        # Period Lock Check
        try:
            closed_period = (
                db.query(AccountingPeriod)
                .filter(
                    AccountingPeriod.client_id == client_id,
                    AccountingPeriod.is_closed.is_(True),
                    AccountingPeriod.start_date <= payload.entry_date,
                    AccountingPeriod.end_date >= payload.entry_date,
                )
                .first()
            )
            if closed_period:
                raise BadRequestException(
                    detail=f"Posting blocked: Accounting period '{closed_period.period_name}' covering date {payload.entry_date} is locked/closed."
                )
        except BadRequestException:
            raise
        except Exception as e:
            if "no such table" in str(e).lower():
                pass
            else:
                raise

        # 1. Duplicate check on accounting_record_id if provided
        if payload.accounting_record_id:
            existing = (
                db.query(JournalEntry)
                .filter(JournalEntry.accounting_record_id == payload.accounting_record_id)
                .first()
            )
            if existing:
                raise ConflictException(
                    detail=f"A journal entry already exists for accounting record {payload.accounting_record_id} (Entry Number: {existing.entry_number})"
                )

        # Document existence verification
        if payload.document_id:
            from app.models.uploaded_document import UploadedDocument
            doc_exists = db.query(UploadedDocument).filter(UploadedDocument.id == payload.document_id).first()
            if not doc_exists:
                raise NotFoundException(detail=f"Source document {payload.document_id} not found")

        # 2. Collect and validate all referenced accounts
        account_ids = {line.account_id for line in payload.lines}
        accounts = (
            db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.id.in_(account_ids))
            .all()
        )
        account_map = {acc.id: acc for acc in accounts}

        for acc_id in account_ids:
            if acc_id not in account_map:
                raise NotFoundException(detail=f"Chart of Accounts account {acc_id} not found")

            acc = account_map[acc_id]
            # Client isolation
            if acc.client_id != client_id:
                raise BadRequestException(
                    detail=f"Account '{acc.account_name}' ({acc.account_code}) does not belong to client {client_id}"
                )
            # Active status
            if not acc.is_active:
                raise BadRequestException(
                    detail=f"Account '{acc.account_name}' ({acc.account_code}) is deactivated and cannot accept postings"
                )

        # 3. Mathematical Double-Entry Balance Verification
        total_dr = sum(line.debit_amount for line in payload.lines)
        total_cr = sum(line.credit_amount for line in payload.lines)

        diff = abs(total_dr - total_cr)
        if diff >= Decimal("0.001"):
            raise BadRequestException(
                detail=f"Double-entry mathematical imbalance: Total Debit (₹{total_dr}) != Total Credit (₹{total_cr}). Difference: ₹{diff}"
            )

        entry_num = cls.generate_next_entry_number(db, client_id, payload.entry_type)
        now_ts = datetime.now(timezone.utc)

        # 4. Create Header
        header = JournalEntry(
            client_id=client_id,
            accounting_record_id=payload.accounting_record_id,
            document_id=payload.document_id,
            entry_number=entry_num,
            entry_date=payload.entry_date,
            entry_type=payload.entry_type.lower(),
            status="posted",
            narration=payload.narration,
            reference_number=payload.reference_number,
            total_debit=total_dr,
            total_credit=total_cr,
            is_balanced=True,
            posted_at=now_ts,
            posted_by_user_id=user.id,
            is_reversed=False,
        )

        db.add(header)
        db.flush()  # assign header.id

        # 5. Create Child Lines (Debits strictly first, followed by Credits)
        sorted_lines = sorted(
            payload.lines,
            key=lambda l: 0 if (l.debit_amount and l.debit_amount > Decimal("0")) else 1
        )
        for idx, line_data in enumerate(sorted_lines, start=1):
            line = JournalEntryLine(
                journal_entry_id=header.id,
                line_number=idx,
                account_id=line_data.account_id,
                debit_amount=line_data.debit_amount,
                credit_amount=line_data.credit_amount,
                description=line_data.description,
                party_name=line_data.party_name,
                party_gstin=line_data.party_gstin,
                tax_head=line_data.tax_head,
                tax_rate=line_data.tax_rate,
            )
            db.add(line)

        if auto_commit:
            db.commit()
            db.refresh(header)
        else:
            db.flush()

        logger.info(
            "Created journal entry %s (%s) for client %s: %d lines, total ₹%s",
            header.entry_number, header.id, client_id, len(payload.lines), total_dr
        )
        return header


    @classmethod
    def get_journal_entries(
        cls,
        db: Session,
        client_id: uuid.UUID,
        user: User,
        entry_type: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[JournalEntry]:
        """Fetch list of journal entries for a client with optional filters."""
        cls.verify_client_access(db, client_id, user)

        query = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client_id)
            .options(joinedload(JournalEntry.lines).joinedload(JournalEntryLine.account))
        )

        if entry_type:
            query = query.filter(JournalEntry.entry_type == entry_type.lower())
        if status and status.lower() not in {"all", "*", ""}:
            query = query.filter(JournalEntry.status == status.lower())
        if from_date:
            query = query.filter(JournalEntry.entry_date >= from_date)
        if to_date:
            query = query.filter(JournalEntry.entry_date <= to_date)

        return query.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc()).all()

    @classmethod
    def get_journal_entry_by_id(cls, db: Session, entry_id: uuid.UUID, user: User) -> JournalEntry:
        """Fetch a specific journal entry by ID with lines and account metadata."""
        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == entry_id)
            .options(joinedload(JournalEntry.lines).joinedload(JournalEntryLine.account))
            .first()
        )
        if not entry:
            raise NotFoundException(detail=f"Journal entry {entry_id} not found")

        cls.verify_client_access(db, entry.client_id, user)
        return entry

    @classmethod
    def reverse_journal_entry(
        cls,
        db: Session,
        entry_id: uuid.UUID,
        reason: str,
        user: User,
    ) -> JournalEntry:
        """
        Reverse a posted journal entry by creating an exact opposite mirror entry.
        Maintains complete immutability of the original entry.
        """
        original = cls.get_journal_entry_by_id(db, entry_id, user)

        if original.is_reversed:
            raise BadRequestException(
                detail=f"Journal entry {original.entry_number} has already been reversed by entry {original.reversal_entry_id}"
            )

        if not reason or not reason.strip():
            raise BadRequestException(detail="A reversal reason is required to maintain audit compliance")

        # Generate reversal number
        reversal_num = f"REV-{original.entry_number}"
        now_ts = datetime.now(timezone.utc)

        # Create reversal header
        reversal_header = JournalEntry(
            client_id=original.client_id,
            accounting_record_id=None,  # Reversal is an independent audit transaction
            document_id=original.document_id,
            entry_number=reversal_num,
            entry_date=date.today(),
            entry_type="journal",
            status="posted",
            narration=f"Reversal of {original.entry_number}. Reason: {reason.strip()}",
            reference_number=f"REV-{original.reference_number or original.entry_number}",
            total_debit=original.total_debit,
            total_credit=original.total_credit,
            is_balanced=True,
            posted_at=now_ts,
            posted_by_user_id=user.id,
            is_reversed=False,
        )

        db.add(reversal_header)
        db.flush()

        # Swap Debits and Credits on every line, ordering Debits first
        swapped_lines = []
        for line in original.lines:
            swapped_lines.append({
                "account_id": line.account_id,
                "debit_amount": line.credit_amount,   # Swapped
                "credit_amount": line.debit_amount,   # Swapped
                "description": f"Reversal leg: {line.description or ''}".strip(),
                "party_name": line.party_name,
                "party_gstin": line.party_gstin,
                "tax_head": line.tax_head,
                "tax_rate": line.tax_rate,
            })
        swapped_lines.sort(
            key=lambda l: 0 if (l["debit_amount"] and l["debit_amount"] > Decimal("0")) else 1
        )
        for idx, s_line in enumerate(swapped_lines, start=1):
            rev_line = JournalEntryLine(
                journal_entry_id=reversal_header.id,
                line_number=idx,
                account_id=s_line["account_id"],
                debit_amount=s_line["debit_amount"],
                credit_amount=s_line["credit_amount"],
                description=s_line["description"],
                party_name=s_line["party_name"],
                party_gstin=s_line["party_gstin"],
                tax_head=s_line["tax_head"],
                tax_rate=s_line["tax_rate"],
            )
            db.add(rev_line)

        # Mark original as reversed
        original.is_reversed = True
        original.reversal_entry_id = reversal_header.id
        original.reversal_reason = reason.strip()

        db.commit()
        db.refresh(reversal_header)

        logger.info(
            "Reversed journal entry %s with reversal entry %s",
            original.entry_number, reversal_header.entry_number
        )
        return reversal_header
