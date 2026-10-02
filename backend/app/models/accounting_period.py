"""
Accounting Period Model — Financial period controls and lockouts.
Enforces fiscal period closure (e.g. FY year-end, quarterly, monthly).
Prevents unauthorized posting into closed or audited periods.
"""

import uuid
from sqlalchemy import Column, String, Date, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    period_name = Column(String(100), nullable=False)  # e.g., "FY 2025-26 Q1", "March 2026"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="open", server_default="open")  # open | closed | locked
    is_closed = Column(Boolean, nullable=False, default=False, server_default="false")
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closing_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────
    client = relationship("Client")
    closed_by_user = relationship("User", foreign_keys=[closed_by_user_id])

    # ── Constraints & Indexes ─────────────────────
    __table_args__ = (
        UniqueConstraint("client_id", "period_name", name="uq_accounting_period_client_name"),
        Index("ix_accounting_period_client_dates", "client_id", "start_date", "end_date"),
        Index("ix_accounting_period_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<AccountingPeriod id={self.id} client={self.client_id} name={self.period_name} status={self.status}>"
