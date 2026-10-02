"""
UploadedDocument Model — stores every document uploaded/scanned via the Invoices module.
Covers all 13 GST document categories. UUID primary key.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Text, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)

    # ── Classification ─────────────────────────────────────────
    # document_category: sales_records | purchase_records | credit_note | debit_note |
    #   b2b_invoice | b2c_invoice | hsn_sac | e_invoice | e_way_bill | gst_challan |
    #   gst_return | gst_notice | document_list
    document_category = Column(String(50), nullable=False, index=True)

    # document_type: upload | scan
    document_type = Column(String(20), nullable=False, default="upload")

    # invoice_type: sales | purchase | credit_note | debit_note | b2b | b2c | other
    invoice_type = Column(String(30), nullable=True)
    # applies_to: sales | purchase (explicit orientation for credit/debit notes)
    applies_to = Column(String(20), nullable=True)

    # ── Core Invoice Fields ────────────────────────────────────
    invoice_number = Column(String(100), nullable=True, index=True)
    gstin = Column(String(20), nullable=True, index=True)
    vendor = Column(String(255), nullable=True)
    customer = Column(String(255), nullable=True)
    invoice_date = Column(String(20), nullable=True)       # stored as string for flexibility

    # ── Financial Fields ───────────────────────────────────────
    amount = Column(Numeric(15, 2), nullable=True)
    taxable_amount = Column(Numeric(15, 2), nullable=True)
    cgst = Column(Numeric(15, 2), nullable=True)
    sgst = Column(Numeric(15, 2), nullable=True)
    igst = Column(Numeric(15, 2), nullable=True)
    cess = Column(Numeric(15, 2), nullable=True)
    hsn = Column(String(50), nullable=True)

    # ── GST Return Fields ──────────────────────────────────────
    gst_return_type = Column(String(20), nullable=True)    # GSTR-1 | GSTR-3B | Annual Return
    financial_year = Column(String(10), nullable=True)
    month = Column(String(20), nullable=True)
    filed_date = Column(String(20), nullable=True)
    arn = Column(String(50), nullable=True)

    # ── Notice Fields ─────────────────────────────────────────
    notice_number = Column(String(100), nullable=True)
    notice_date = Column(String(20), nullable=True)
    response_due_date = Column(String(20), nullable=True)
    priority = Column(String(20), nullable=True)           # low | medium | high

    # ── File Storage ──────────────────────────────────────────
    file_name = Column(String(255), nullable=True)
    file_path = Column(String(1000), nullable=True)        # relative path in uploads dir
    file_size = Column(String(20), nullable=True)          # human-readable e.g. "1.2 MB"
    file_type = Column(String(20), nullable=True)          # pdf | image | excel | json | xml

    # ── OCR ───────────────────────────────────────────────────
    ocr_status = Column(String(20), nullable=True, default="pending")  # pending | processing | done | failed
    ocr_confidence = Column(Numeric(5, 2), nullable=True)
    ocr_text = Column(Text, nullable=True)

    # ── Status & Meta ─────────────────────────────────────────
    status = Column(String(20), nullable=False, default="pending")     # pending | processed | verified | rejected
    uploaded_by = Column(String(255), nullable=True)
    metadata_ = Column("metadata", Text, nullable=True)                # JSON blob for extra fields

    # ── Timestamps ────────────────────────────────────────────
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────────────────
    client = relationship("Client", back_populates="uploaded_documents")
    journal_entries = relationship("JournalEntry", back_populates="document")


    __table_args__ = (
        Index("ix_uploaded_doc_client_cat", "client_id", "document_category"),
        Index("ix_uploaded_doc_gstin", "gstin"),
        Index("ix_uploaded_doc_invoice_number", "invoice_number"),
        Index("ix_uploaded_doc_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<UploadedDocument id={self.id} category={self.document_category} client={self.client_id}>"
