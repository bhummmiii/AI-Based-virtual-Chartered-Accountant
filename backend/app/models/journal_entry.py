"""
Journal Entry Models — Persistent, double-entry general journal header and line items.
Enforces double-entry equation (Total Debit == Total Credit) at the database layer.
Directly integrates with the Chart of Accounts master.
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Date,
    Numeric,
    Text,
    Boolean,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class JournalEntry(Base):
    """
    Journal Entry Header — Represents a complete, balanced accounting transaction.
    Every posted journal entry must satisfy: sum(debit_lines) == sum(credit_lines).
    """
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    accounting_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounting_records.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("uploaded_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entry_number = Column(String(50), nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    entry_type = Column(String(30), nullable=False)  # sales | purchase | payment | receipt | journal | contra
    status = Column(String(20), nullable=False, default="posted", server_default="posted")  # draft | posted | reversed
    narration = Column(Text, nullable=True)
    reference_number = Column(String(100), nullable=True, index=True)
    total_debit = Column(Numeric(15, 2), nullable=False, default=0.00)
    total_credit = Column(Numeric(15, 2), nullable=False, default=0.00)
    is_balanced = Column(Boolean, nullable=False, default=True, server_default="true")
    posted_at = Column(DateTime(timezone=True), nullable=True)
    posted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_reversed = Column(Boolean, nullable=False, default=False, server_default="false")
    reversal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    reversal_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────
    client = relationship("Client", back_populates="journal_entries")
    accounting_record = relationship("AccountingRecord", back_populates="journal_entry")
    document = relationship("UploadedDocument", back_populates="journal_entries")
    posted_by_user = relationship("User", foreign_keys=[posted_by_user_id])
    reversal_entry = relationship("JournalEntry", remote_side=[id], foreign_keys=[reversal_entry_id])
    lines = relationship(
        "JournalEntryLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.line_number",
    )

    # ── Constraints & Indexes ─────────────────────
    __table_args__ = (
        UniqueConstraint("client_id", "entry_number", name="uq_journal_entry_client_number"),
        UniqueConstraint("accounting_record_id", name="uq_journal_entry_accounting_record"),
        CheckConstraint("total_debit >= 0 AND total_credit >= 0", name="chk_journal_entry_non_negative"),
        CheckConstraint("total_debit = total_credit", name="chk_journal_entry_balanced"),
        Index("ix_journal_client_date", "client_id", "entry_date"),
        Index("ix_journal_client_type", "client_id", "entry_type"),
        Index("ix_journal_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<JournalEntry id={self.id} client={self.client_id} number={self.entry_number} type={self.entry_type} total={self.total_debit}>"


class JournalEntryLine(Base):
    """
    Journal Entry Line — Atomized debit or credit leg of a financial transaction.
    Must link to a valid account in chart_of_accounts.
    """
    __tablename__ = "journal_entry_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    journal_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_number = Column(Integer, nullable=False)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    debit_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    credit_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    description = Column(Text, nullable=True)
    party_name = Column(String(255), nullable=True)
    party_gstin = Column(String(20), nullable=True)
    tax_head = Column(String(20), nullable=True)  # cgst | sgst | igst | cess
    tax_rate = Column(Numeric(5, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────
    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("ChartOfAccounts", back_populates="journal_lines")

    # ── Constraints & Indexes ─────────────────────
    __table_args__ = (
        UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_line_entry_seq"),
        CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="chk_journal_line_non_negative"),
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="chk_journal_line_single_sided",
        ),
        Index("ix_journal_lines_account_id", "account_id"),
        Index("ix_journal_lines_tax_head", "tax_head"),
    )

    def __repr__(self) -> str:
        return f"<JournalEntryLine id={self.id} entry={self.journal_entry_id} line={self.line_number} Dr={self.debit_amount} Cr={self.credit_amount}>"
