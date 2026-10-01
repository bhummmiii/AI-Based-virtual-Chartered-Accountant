"""
Chart of Accounts Model — Persistent, client-isolated financial account master.
Adheres to ICAI accounting classifications (Asset, Liability, Equity, Revenue, Expense).
Supports hierarchical parent-subaccount relationships.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class ChartOfAccounts(Base):
    __tablename__ = "chart_of_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    account_code = Column(String(50), nullable=False)
    account_name = Column(String(255), nullable=False)
    account_type = Column(String(50), nullable=False)       # asset | liability | equity | revenue | expense
    account_subgroup = Column(String(100), nullable=True)   # current_assets | sundry_debtors | bank_accounts | duties_and_taxes | etc.
    role = Column(String(50), nullable=True, index=True)   # OUTPUT_CGST, OUTPUT_SGST, OUTPUT_IGST, INPUT_CGST, INPUT_SGST, INPUT_IGST, SALES, SALES_RETURN, PURCHASE, PURCHASE_RETURN, DEBTORS, CREDITORS, OTHER_INCOME
    parent_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_system = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────
    client = relationship("Client", back_populates="chart_of_accounts")
    parent_account = relationship("ChartOfAccounts", remote_side=[id], backref="sub_accounts")
    journal_lines = relationship("JournalEntryLine", back_populates="account")


    # ── Constraints & Indexes ─────────────────────
    __table_args__ = (
        UniqueConstraint("client_id", "account_code", name="uq_coa_client_code"),
        UniqueConstraint("client_id", "account_name", name="uq_coa_client_name"),
        Index("ix_coa_client_type", "client_id", "account_type"),
        Index("ix_coa_client_active", "client_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ChartOfAccounts id={self.id} client={self.client_id} code={self.account_code} name={self.account_name}>"
