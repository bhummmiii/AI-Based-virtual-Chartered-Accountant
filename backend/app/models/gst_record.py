"""
GST Record Model — GST filing records with tax component breakdown.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Date, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class GSTRecord(Base):
    __tablename__ = "gst_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    gst_period = Column(String(20), nullable=False)           # e.g. "2026-07", "Q1-2026"
    gst_type = Column(String(30), nullable=False, default="GSTR-3B")  # GSTR-1 | GSTR-3B | GSTR-9 | GSTR-9C
    taxable_amount = Column(Numeric(15, 2), nullable=False, default=0)
    cgst = Column(Numeric(15, 2), nullable=False, default=0)  # Central GST
    sgst = Column(Numeric(15, 2), nullable=False, default=0)  # State GST
    igst = Column(Numeric(15, 2), nullable=False, default=0)  # Integrated GST
    total_tax = Column(Numeric(15, 2), nullable=False, default=0)
    filing_status = Column(String(20), nullable=False, default="pending")  # filed | pending | overdue | nil
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────
    client = relationship("Client", back_populates="gst_records")

    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_gst_client_period", "client_id", "gst_period"),
        Index("ix_gst_filing_status", "filing_status"),
    )

    def __repr__(self) -> str:
        return f"<GSTRecord id={self.id} client={self.client_id} period={self.gst_period} status={self.filing_status}>"
