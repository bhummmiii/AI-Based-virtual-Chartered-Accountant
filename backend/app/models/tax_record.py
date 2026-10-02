"""
Tax Record Model — Income tax and TDS records per client per financial year.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class TaxRecord(Base):
    __tablename__ = "tax_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    financial_year = Column(String(10), nullable=False)    # e.g. "2025-26"
    tax_type = Column(String(50), nullable=False)          # income_tax | tds | advance_tax | corporate_tax
    taxable_income = Column(Numeric(15, 2), nullable=False, default=0)
    tds = Column(Numeric(15, 2), nullable=False, default=0)
    advance_tax = Column(Numeric(15, 2), nullable=False, default=0)
    total_tax = Column(Numeric(15, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")  # filed | pending | overdue | exempt
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────
    client = relationship("Client", back_populates="tax_records")

    # ── Indexes ───────────────────────────────────
    __table_args__ = (
        Index("ix_tax_client_fy", "client_id", "financial_year"),
        Index("ix_tax_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<TaxRecord id={self.id} client={self.client_id} fy={self.financial_year} status={self.status}>"
