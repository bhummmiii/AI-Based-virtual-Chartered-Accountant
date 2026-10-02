"""
Invoice Model — Client invoices with OCR and translation support.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Date, Numeric, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number = Column(String(100), nullable=False, index=True)
    vendor_name = Column(String(255), nullable=False)
    invoice_date = Column(Date, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False, default=0)
    currency = Column(String(10), nullable=False, default="INR")
    ocr_text = Column(Text, nullable=True)                 # raw OCR output
    translated_text = Column(Text, nullable=True)          # translated OCR text
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────
    client = relationship("Client", back_populates="invoices")

    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_invoice_client_date", "client_id", "invoice_date"),
        Index("ix_invoice_number", "invoice_number"),
    )

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} number={self.invoice_number} vendor={self.vendor_name}>"
