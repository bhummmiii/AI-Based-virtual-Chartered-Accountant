"""
Accounting Record Model — Double-entry ledger transactions per client.
Many records belong to one client.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Date, Numeric, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class AccountingRecord(Base):
    __tablename__ = "accounting_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False)
    voucher_type = Column(String(50), nullable=False)     # receipt | payment | journal | contra | sales | purchase
    description = Column(Text, nullable=True)
    debit = Column(Numeric(15, 2), nullable=False, default=0)
    credit = Column(Numeric(15, 2), nullable=False, default=0)
    category = Column(String(100), nullable=True)         # salary | rent | utilities | sales | tax | misc
    document_id = Column(UUID(as_uuid=True), ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), nullable=False, default="draft", server_default="draft")  # draft | posted
    reference_number = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────
    client = relationship("Client", back_populates="accounting_records")
    document = relationship("UploadedDocument", foreign_keys=[document_id])
    journal_entry = relationship("JournalEntry", back_populates="accounting_record", uselist=False)


    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_accounting_client_date", "client_id", "transaction_date"),
        Index("ix_accounting_voucher_type", "voucher_type"),
        Index("ix_accounting_records_document_id", "document_id"),
        Index("ix_accounting_records_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<AccountingRecord id={self.id} client={self.client_id} type={self.voucher_type}>"
